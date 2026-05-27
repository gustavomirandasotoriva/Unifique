import os
import sys

# Força UTF-8 no terminal Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

load_dotenv()

BASE_URL = "https://servicos.unifique.com.br"
LOGIN_URL = f"{BASE_URL}/login/in/Lw=="
console = Console()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}


def get_credentials():
    cpf = os.getenv("UNIFIQUE_CPF")
    senha = os.getenv("UNIFIQUE_SENHA")
    if not cpf or not senha:
        console.print("[red]Erro:[/red] Defina UNIFIQUE_CPF e UNIFIQUE_SENHA no arquivo .env")
        sys.exit(1)
    return cpf, senha


def fazer_login(session, cpf, senha):
    console.print("[yellow]Conectando ao portal Unifique...[/yellow]")

    resp = session.get(LOGIN_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Coleta campos ocultos (CSRF tokens, etc.)
    form = soup.find("form")
    payload = {}
    if form:
        for inp in form.find_all("input", type="hidden"):
            nome = inp.get("name")
            valor = inp.get("value", "")
            if nome:
                payload[nome] = valor

        action = form.get("action", LOGIN_URL)
        post_url = action if action.startswith("http") else BASE_URL + action
    else:
        post_url = LOGIN_URL

    payload["login_cpfcnpj"] = cpf
    payload["login_senha"] = senha

    console.print("[yellow]Fazendo login...[/yellow]")
    resp_login = session.post(
        post_url,
        data=payload,
        headers={**HEADERS, "Referer": LOGIN_URL},
        timeout=15,
        allow_redirects=True,
    )
    resp_login.raise_for_status()

    url_final = resp_login.url
    console.print(f"[dim]URL após login: {url_final}[/dim]")

    # Verifica se ainda está na página de login
    if "/login" in url_final and "in/" in url_final:
        soup_erro = BeautifulSoup(resp_login.text, "html.parser")
        mensagem = ""
        for seletor in ["[class*='erro']", "[class*='error']", "[class*='alert']", ".mensagem"]:
            el = soup_erro.select_one(seletor)
            if el:
                mensagem = el.get_text(strip=True)
                break
        console.print(f"[red]Login falhou.[/red] {mensagem or 'Verifique CPF e senha no arquivo .env'}")
        sys.exit(1)

    console.print("[green]Login realizado com sucesso![/green]")
    return resp_login


def encontrar_url_cobrancas(session, resp_login):
    soup = BeautifulSoup(resp_login.text, "html.parser")

    soup = BeautifulSoup(resp_login.text, "html.parser")

    # Prioriza links de "em aberto" antes de qualquer cobrança
    termos_prioridade = ["em aberto", "aberto", "pendente", "venc"]
    termos_gerais = ["cobran", "financ", "boleto", "fatura"]

    todos_links = soup.find_all("a", href=True)

    for termos in [termos_prioridade, termos_gerais]:
        for link in todos_links:
            href = link["href"].lower()
            texto = link.get_text(strip=True).lower()
            if any(t in href or t in texto for t in termos):
                url = link["href"] if link["href"].startswith("http") else BASE_URL + link["href"]
                console.print(f"[dim]Link de cobranças: {url}[/dim]")
                return url

    # Tenta URLs diretas comuns
    tentativas = [
        f"{BASE_URL}/cobrancas/em-aberto/",
        f"{BASE_URL}/cobrancas/aberto/",
        f"{BASE_URL}/cobrancas/",
        f"{BASE_URL}/financeiro/em-aberto/",
        f"{BASE_URL}/cliente/cobrancas",
        f"{BASE_URL}/boletos",
    ]
    for url in tentativas:
        r = session.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200 and "/login" not in r.url:
            console.print(f"[dim]URL encontrada: {url}[/dim]")
            return url

    return None


def extrair_cobrancas(session, url):
    console.print(f"[yellow]Buscando cobranças em aberto...[/yellow]")
    resp = session.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Tenta encontrar tabela
    tabelas = soup.find_all("table")
    if not tabelas:
        # Tenta extrair cards/divs com info de cobrança
        console.print("[yellow]Nenhuma tabela encontrada. Exibindo texto da página:[/yellow]")
        console.print(soup.get_text(separator="\n", strip=True)[:2000])
        return [], []

    tabela = tabelas[0]
    linhas = tabela.find_all("tr")

    cabecalho = []
    ths = linhas[0].find_all(["th", "td"]) if linhas else []
    cabecalho = [th.get_text(strip=True) for th in ths]

    # Substitui cabeçalho vazio (coluna de ações) por "Ações"
    cabecalho = [c if c else "Ações" for c in cabecalho]

    dados = []
    for linha in linhas[1:]:
        celulas = linha.find_all("td")
        if celulas:
            linha_dados = []
            for i, cel in enumerate(celulas):
                # Coluna de ações: extrai só os textos dos links
                col_nome = cabecalho[i] if i < len(cabecalho) else ""
                if col_nome == "Ações" or not col_nome:
                    links_texto = [a.get_text(strip=True) for a in cel.find_all("a") if a.get_text(strip=True)]
                    linha_dados.append(" | ".join(links_texto) if links_texto else cel.get_text(strip=True))
                else:
                    linha_dados.append(cel.get_text(strip=True))
            dados.append(linha_dados)

    return cabecalho, dados


def exibir_tabela(cabecalho, dados):
    console.print()
    if not dados:
        console.print(Panel("[green]Nenhuma cobrança em aberto![/green]", expand=False))
        return

    tabela = Table(
        title="Cobranças em Aberto — Unifique",
        box=box.ROUNDED,
        show_lines=True,
        highlight=True,
    )

    cols = cabecalho if cabecalho else [f"Coluna {i+1}" for i in range(len(dados[0]))]
    estilos = ["cyan", "green", "yellow", "magenta", "white"]
    for i, col in enumerate(cols):
        tabela.add_column(col, style=estilos[i % len(estilos)])

    for linha in dados:
        while len(linha) < len(tabela.columns):
            linha.append("")
        tabela.add_row(*linha[:len(tabela.columns)])

    console.print(tabela)
    console.print(f"\n[bold]Total: {len(dados)} cobrança(s) em aberto[/bold]\n")


def main():
    cpf, senha = get_credentials()

    console.print(Panel.fit(
        "[bold blue]Unifique — Cobranças em Aberto[/bold blue]",
        border_style="blue",
    ))

    session = requests.Session()

    resp_login = fazer_login(session, cpf, senha)
    url_cobrancas = encontrar_url_cobrancas(session, resp_login)

    if not url_cobrancas:
        console.print("[red]Não foi possível encontrar a seção de cobranças.[/red]")
        console.print("O site pode ter mudado de estrutura.")
        sys.exit(1)

    cabecalho, dados = extrair_cobrancas(session, url_cobrancas)
    exibir_tabela(cabecalho, dados)


if __name__ == "__main__":
    main()
