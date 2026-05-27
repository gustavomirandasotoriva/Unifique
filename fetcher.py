import re
import json
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://servicos.unifique.com.br"
LOGIN_URL = f"{BASE_URL}/login/in/Lw=="

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}


class LoginError(Exception):
    pass


class CobrancasError(Exception):
    pass


class UnifiqueClient:
    def __init__(self):
        self.session = requests.Session()

    def login(self, cpf: str, senha: str):
        resp = self.session.get(LOGIN_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        form = soup.find("form")
        payload = {}
        post_url = LOGIN_URL

        if form:
            for inp in form.find_all("input", type="hidden"):
                nome = inp.get("name")
                if nome:
                    payload[nome] = inp.get("value", "")
            action = form.get("action", LOGIN_URL)
            post_url = action if action.startswith("http") else BASE_URL + action

        payload["login_cpfcnpj"] = cpf
        payload["login_senha"] = senha

        resp_login = self.session.post(
            post_url,
            data=payload,
            headers={**HEADERS, "Referer": LOGIN_URL},
            timeout=15,
            allow_redirects=True,
        )
        resp_login.raise_for_status()

        if "/login" in resp_login.url and "in/" in resp_login.url:
            soup_err = BeautifulSoup(resp_login.text, "html.parser")
            msg = ""
            for sel in ["[class*='erro']", "[class*='error']", "[class*='alert']"]:
                el = soup_err.select_one(sel)
                if el:
                    msg = el.get_text(strip=True)
                    break
            raise LoginError(msg or "CPF/CNPJ ou senha incorretos.")

        return resp_login

    def get_cobrancas(self, cpf: str, senha: str):
        resp_login = self.login(cpf, senha)
        soup_home = BeautifulSoup(resp_login.text, "html.parser")
        url_cob = self._encontrar_url_cobrancas(soup_home)

        if not url_cob:
            raise CobrancasError("Não foi possível localizar a seção de cobranças.")

        resp = self.session.get(url_cob, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return self._extrair_tabela(resp.text)

    def get_pix(self, codcliente: int, codcobranca: int) -> dict:
        """Busca o código Pix via API do portal."""
        url = f"{BASE_URL}/cobrancas/pix.php?codcliente={codcliente}&codcobranca={codcobranca}&tipo=txt"
        resp = self.session.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return {
            "pix_code": data.get("code"),
            "valor_original": data.get("amount"),
            "juros_multa": data.get("fees", 0),
            "dias_atraso": data.get("JurosMulta", {}).get("nr_dias_atrasado", 0),
        }

    def get_boleto_url(self, boleto_key: str) -> str:
        """Retorna a URL do boleto. O path correto é /cobrancas/boleto/ (relativo a /cobrancas/abertas/)."""
        return f"{BASE_URL}/cobrancas/boleto/{boleto_key}/"

    def get_boleto_info(self, boleto_key: str) -> dict:
        """Busca a linha digitável do boleto via portal autenticado."""
        url = self.get_boleto_url(boleto_key)
        resp = self.session.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200 or "/login" in resp.url:
            raise CobrancasError("Boleto não disponível.")

        soup = BeautifulSoup(resp.text, "html.parser")

        # Procura linha digitável em inputs, spans, divs, tds
        for el in soup.find_all(["input", "span", "p", "div", "td", "strong", "b"]):
            txt = el.get("value", "") or el.get_text(strip=True)
            m = re.search(r"\d[\d\s.]{44,}\d", txt)
            if m:
                codigo = re.sub(r"\s+", " ", m.group()).strip()
                return {"linha_digitavel": codigo, "url": url}

        # Busca em todo o texto da página como fallback
        m = re.search(r"\d[\d\s.]{44,}\d", soup.get_text())
        if m:
            codigo = re.sub(r"\s+", " ", m.group()).strip()
            return {"linha_digitavel": codigo, "url": url}

        return {"linha_digitavel": None, "url": url}

    # ─── helpers ────────────────────────────────────────────

    def _encontrar_url_cobrancas(self, soup) -> str | None:
        termos_prio = ["em aberto", "abertas", "aberto", "pendente"]
        termos = ["cobran", "financ", "boleto", "fatura"]

        links = soup.find_all("a", href=True)
        for group in [termos_prio, termos]:
            for link in links:
                href = link["href"].lower()
                txt = link.get_text(strip=True).lower()
                if any(t in href or t in txt for t in group):
                    return link["href"] if link["href"].startswith("http") else BASE_URL + link["href"]

        for url in [f"{BASE_URL}/cobrancas/abertas/", f"{BASE_URL}/cobrancas/"]:
            r = self.session.get(url, headers=HEADERS, timeout=10)
            if r.status_code == 200 and "/login" not in r.url:
                return url
        return None

    def _extrair_tabela(self, html: str):
        """Retorna (cabecalho, dados, pagamentos).
        pagamentos: lista de dicts por linha com codcliente, codcobranca, boleto_key
        """
        soup = BeautifulSoup(html, "html.parser")
        tabelas = soup.find_all("table")
        if not tabelas:
            return [], [], []

        linhas = tabelas[0].find_all("tr")
        if not linhas:
            return [], [], []

        ths = linhas[0].find_all(["th", "td"])
        cabecalho = [th.get_text(strip=True) or "Ações" for th in ths]

        dados = []
        pagamentos = []

        for linha in linhas[1:]:
            celulas = linha.find_all("td")
            if not celulas:
                continue

            linha_dados = []
            info_pag = {"codcliente": None, "codcobranca": None, "boleto_key": None, "linha_digitavel": None}

            for i, cel in enumerate(celulas):
                col = cabecalho[i] if i < len(cabecalho) else ""
                if col == "Ações" or not col:
                    textos = [a.get_text(strip=True) for a in cel.find_all("a") if a.get_text(strip=True)]
                    linha_dados.append(" | ".join(textos) if textos else cel.get_text(strip=True))
                else:
                    linha_dados.append(cel.get_text(strip=True))

            # Extrai dados de pagamento de TODOS os botões modais (data-content)
            # Não quebra no primeiro — mescla campos de todos os modais da linha
            for a in linha.find_all("a", {"data-content": True}):
                content_html = a.get("data-content", "")
                parcial = _parse_payment_info(content_html)
                for k, v in parcial.items():
                    if v is not None and info_pag.get(k) is None:
                        info_pag[k] = v

            dados.append(linha_dados)
            pagamentos.append(info_pag)

        return cabecalho, dados, pagamentos


def _parse_payment_info(html: str) -> dict:
    """Extrai codcliente, codcobranca, boleto_key e linha_digitavel do HTML do data-content."""
    info = {"codcliente": None, "codcobranca": None, "boleto_key": None, "linha_digitavel": None}

    # click_pix(codcliente, codcobranca, ...)
    m = re.search(r"click_pix\((\d+)\s*,\s*(\d+)", html)
    if m:
        info["codcliente"] = int(m.group(1))
        info["codcobranca"] = int(m.group(2))

    # href='../boleto/KEY/' ou href='/boleto/KEY/'
    m = re.search(r"href=['\"](?:\.\.)?/boleto/([^/'\"]+)/?['\"]", html)
    if m:
        info["boleto_key"] = m.group(1)

    # fallback: registraLog(*, codcobranca)
    if not info["codcobranca"]:
        m = re.search(r"registraLog\([^,]+,\s*(\d+)\)", html)
        if m:
            info["codcobranca"] = int(m.group(1))

    # Linha digitável: formato "DDDDD.DDDDD DDDDD.DDDDDD DDDDD.DDDDDD D DDDDDDDDDDDDDD"
    m = re.search(r"\d{5}\.\d{5}\s+\d{5}\.\d{6}\s+\d{5}\.\d{6}\s+\d\s+\d{14}", html)
    if not m:
        # Formato alternativo com hífen ou outros separadores
        m = re.search(r"\d{4,5}[\.\s]\d{4,5}[\.\s]\d{4,5}[\.\s]\d{4,5}[\.\s]\d{4,5}", html)
    if not m:
        # 47 dígitos consecutivos (sem formatação)
        m = re.search(r"\b\d{47}\b", html)
    if not m:
        # Linha em input value="..."
        m = re.search(r'value=["\'](\d[\d\s.]{40,}\d)["\']', html)
        if m:
            info["linha_digitavel"] = re.sub(r"\s+", " ", m.group(1)).strip()
            return info
    if m:
        info["linha_digitavel"] = re.sub(r"\s+", " ", m.group()).strip()

    return info


# Instância global (mantém sessão)
client = UnifiqueClient()


def buscar_cobrancas_completo(cpf: str, senha: str):
    return client.get_cobrancas(cpf, senha)


def buscar_pix(codcliente: int, codcobranca: int) -> dict:
    return client.get_pix(codcliente, codcobranca)


def get_boleto_url(boleto_key: str) -> str:
    return client.get_boleto_url(boleto_key)


def get_boleto_info(boleto_key: str) -> dict:
    return client.get_boleto_info(boleto_key)
