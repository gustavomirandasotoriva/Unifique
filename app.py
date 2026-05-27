import os
import sys
from io import BytesIO
from dotenv import load_dotenv

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QScrollArea,
    QMessageBox, QDialog, QLineEdit, QProgressBar,
    QStatusBar, QGridLayout,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QUrl
from PyQt6.QtGui import QPixmap
from PyQt6.QtWebEngineWidgets import QWebEngineView

load_dotenv()
import fetcher

UNI_BLUE   = "#253A76"
UNI_BLUE2  = "#1a2d5e"
UNI_ACCENT = "#0ea5e9"
BG         = "#eef2ff"
CARD_BG    = "#ffffff"
TEXT_MAIN  = "#0f172a"
TEXT_GRAY  = "#64748b"
SUCCESS    = "#22c55e"
WARNING    = "#ef4444"
BORDER     = "#dde3f0"


# ──────────────────────────────────────────────────────────────
# Threads
# ──────────────────────────────────────────────────────────────
class BuscaThread(QThread):
    concluido = pyqtSignal(list, list, list)
    erro = pyqtSignal(str)

    def __init__(self, cpf, senha):
        super().__init__()
        self.cpf = cpf
        self.senha = senha

    def run(self):
        try:
            cab, dados, pag = fetcher.buscar_cobrancas_completo(self.cpf, self.senha)
            self.concluido.emit(cab, dados, pag)
        except Exception as e:
            self.erro.emit(str(e))


class PixThread(QThread):
    concluido = pyqtSignal(dict)
    erro = pyqtSignal(str)

    def __init__(self, codcliente, codcobranca):
        super().__init__()
        self.codcliente = codcliente
        self.codcobranca = codcobranca

    def run(self):
        try:
            self.concluido.emit(fetcher.buscar_pix(self.codcliente, self.codcobranca))
        except Exception as e:
            self.erro.emit(str(e))


# ──────────────────────────────────────────────────────────────
# QR Code helper
# ──────────────────────────────────────────────────────────────
def gerar_qr_pixmap(texto: str, size: int = 260) -> QPixmap | None:
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=8, border=3,
                           error_correction=qrcode.constants.ERROR_CORRECT_L)
        qr.add_data(texto)
        qr.make(fit=True)
        img = qr.make_image(fill_color=UNI_BLUE, back_color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")
        px = QPixmap()
        px.loadFromData(buf.getvalue())
        return px.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────
# Diálogo Pix
# ──────────────────────────────────────────────────────────────
class PixDialog(QDialog):
    def __init__(self, pix_code: str, info: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pagar com Pix")
        self.setFixedWidth(420)
        self.setStyleSheet(f"background:{CARD_BG}; font-family:'Segoe UI';")

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(16)

        hdr = QHBoxLayout()
        dot = QLabel("●")
        dot.setStyleSheet(f"color:{UNI_ACCENT}; font-size:20px;")
        title = QLabel("Pagar com Pix")
        title.setStyleSheet(f"font-size:18px; font-weight:700; color:{TEXT_MAIN};")
        hdr.addWidget(dot)
        hdr.addWidget(title)
        hdr.addStretch()
        root.addLayout(hdr)

        valor = info.get("valor_original", 0) or 0
        juros = info.get("juros_multa", 0) or 0
        dias  = info.get("dias_atraso", 0) or 0

        val_box = QFrame()
        val_box.setStyleSheet(
            f"background:{BG}; border-radius:10px; border:1px solid {BORDER};"
        )
        val_layout = QVBoxLayout(val_box)
        val_layout.setContentsMargins(16, 12, 16, 12)

        lbl_total = QLabel(f"R$ {valor:.2f}".replace(".", ","))
        lbl_total.setStyleSheet(f"font-size:28px; font-weight:700; color:{UNI_BLUE};")
        lbl_total.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val_layout.addWidget(lbl_total)

        if dias > 0:
            lbl_juros = QLabel(f"⚠ {dias} dias em atraso · Juros/multa: R$ {juros:.2f}".replace(".", ","))
            lbl_juros.setStyleSheet(f"font-size:11px; color:{WARNING}; font-weight:500;")
            lbl_juros.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val_layout.addWidget(lbl_juros)

        root.addWidget(val_box)

        qr_lbl = QLabel()
        qr_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        px = gerar_qr_pixmap(pix_code)
        if px:
            qr_lbl.setPixmap(px)
        else:
            qr_lbl.setText("QR Code indisponível")
        root.addWidget(qr_lbl)

        lbl_cc = QLabel("Pix Copia e Cola")
        lbl_cc.setStyleSheet(f"font-size:12px; font-weight:600; color:{TEXT_GRAY};")
        root.addWidget(lbl_cc)

        row_pix = QHBoxLayout()
        self.campo_pix = QLineEdit(pix_code)
        self.campo_pix.setReadOnly(True)
        self.campo_pix.setStyleSheet(
            f"background:{BG}; border:1px solid {BORDER}; border-radius:8px;"
            f"padding:8px 12px; font-size:11px; color:{TEXT_MAIN};"
        )
        btn_copiar = QPushButton("Copiar")
        btn_copiar.setFixedHeight(36)
        btn_copiar.setFixedWidth(72)
        btn_copiar.setStyleSheet(
            f"background:{UNI_BLUE}; color:white; border:none; border-radius:8px;"
            f"font-size:12px; font-weight:600;"
        )
        btn_copiar.clicked.connect(self._copiar)
        row_pix.addWidget(self.campo_pix)
        row_pix.addWidget(btn_copiar)
        root.addLayout(row_pix)

        btn_fechar = QPushButton("Fechar")
        btn_fechar.setFixedHeight(40)
        btn_fechar.setStyleSheet(
            f"background:{BG}; color:{TEXT_GRAY}; border:1px solid {BORDER};"
            f"border-radius:8px; font-size:13px;"
        )
        btn_fechar.clicked.connect(self.accept)
        root.addWidget(btn_fechar)

    def _copiar(self):
        QApplication.clipboard().setText(self.campo_pix.text())
        QMessageBox.information(self, "Copiado!", "Código Pix copiado para a área de transferência.")


# ──────────────────────────────────────────────────────────────
# Diálogo Boleto
# ──────────────────────────────────────────────────────────────
class BoletoDialog(QDialog):
    _LOGIN_URL = "https://servicos.unifique.com.br/login/in/Lw=="

    def __init__(self, boleto_url: str, cpf: str, senha: str, parent=None):
        super().__init__(parent)
        self._boleto_url = boleto_url
        self._cpf   = cpf.replace("'", "")
        self._senha = senha.replace("'", "")
        self._logged = False

        self.setWindowTitle("Boleto — Unifique")
        self.resize(940, 680)
        self.setStyleSheet(f"background:{CARD_BG};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QWidget()
        bar.setFixedHeight(48)
        bar.setStyleSheet(f"background:{UNI_BLUE};")
        bar_l = QHBoxLayout(bar)
        bar_l.setContentsMargins(16, 0, 16, 0)
        self._lbl_status = QLabel("Conectando ao portal…")
        self._lbl_status.setStyleSheet("color:white; font-size:13px; font-weight:600;")
        btn_fechar = QPushButton("✕  Fechar")
        btn_fechar.setFixedHeight(32)
        btn_fechar.setStyleSheet(
            "background:rgba(255,255,255,0.15); color:white; border:none;"
            "border-radius:6px; padding:0 12px; font-size:12px;"
        )
        btn_fechar.clicked.connect(self.accept)
        bar_l.addWidget(self._lbl_status)
        bar_l.addStretch()
        bar_l.addWidget(btn_fechar)
        root.addWidget(bar)

        self._view = QWebEngineView()
        self._view.loadFinished.connect(self._on_load)
        self._view.load(QUrl(self._LOGIN_URL))
        root.addWidget(self._view, 1)

    def _on_load(self, ok: bool):
        url = self._view.url().toString()

        if not self._logged and ("login" in url or url == self._LOGIN_URL):
            self._lbl_status.setText("Autenticando…")
            js = f"""
                (function() {{
                    var cpf  = document.querySelector('[name="login_cpfcnpj"]');
                    var pwd  = document.querySelector('[name="login_senha"]');
                    var form = document.querySelector('form');
                    if (cpf && pwd && form) {{
                        cpf.value  = '{self._cpf}';
                        pwd.value  = '{self._senha}';
                        form.submit();
                    }}
                }})();
            """
            self._view.page().runJavaScript(js)

        elif not self._logged and "login" not in url:
            self._logged = True
            self._lbl_status.setText("Carregando boleto…")
            self._view.load(QUrl(self._boleto_url))

        elif self._logged:
            self._lbl_status.setText("Boleto")


# ──────────────────────────────────────────────────────────────
# Stat Card (resumo no topo)
# ──────────────────────────────────────────────────────────────
class StatCard(QFrame):
    def __init__(self, titulo: str, valor: str, accent: str, parent=None):
        super().__init__(parent)
        self.setObjectName("statcard")
        self.setMinimumWidth(180)
        self.setFixedHeight(110)
        self.setStyleSheet(f"""
            QFrame#statcard {{
                background:{CARD_BG};
                border:1px solid {BORDER};
                border-top: 3px solid {accent};
                border-radius:12px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 14)
        root.setSpacing(8)

        lbl_title = QLabel(titulo)
        lbl_title.setStyleSheet(f"font-size:13px; color:{TEXT_GRAY};")
        root.addWidget(lbl_title)

        self.lbl_valor = QLabel(valor)
        self.lbl_valor.setStyleSheet(f"font-size:26px; font-weight:700; color:{TEXT_MAIN};")
        root.addWidget(self.lbl_valor)

    def set_valor(self, valor: str):
        self.lbl_valor.setText(valor)


# ──────────────────────────────────────────────────────────────
# Card de cobrança
# ──────────────────────────────────────────────────────────────
class CobrancaCard(QFrame):
    pix_clicked    = pyqtSignal(int, int)
    boleto_clicked = pyqtSignal(object)

    def __init__(self, dados: list, cabecalho: list, pag: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setStyleSheet(f"""
            QFrame#card {{
                background:{CARD_BG};
                border:1px solid {BORDER};
                border-left: 4px solid {UNI_ACCENT};
                border-radius:12px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        # Header: descrição
        desc_idx = next((i for i, h in enumerate(cabecalho) if "desc" in h.lower()), 0)
        desc = dados[desc_idx] if desc_idx < len(dados) else dados[0] if dados else "Cobrança"
        desc_curta = desc.split("(")[0].strip()

        lbl_desc = QLabel(desc_curta)
        lbl_desc.setStyleSheet(f"font-size:13px; color:{TEXT_GRAY};")
        lbl_desc.setWordWrap(True)
        root.addWidget(lbl_desc)

        # Valor grande
        val_idx = next((i for i, h in enumerate(cabecalho) if "valor" in h.lower()), -1)
        valor_txt = dados[val_idx] if val_idx != -1 and val_idx < len(dados) else ""
        lbl_valor = QLabel(valor_txt)
        lbl_valor.setStyleSheet(f"font-size:26px; font-weight:700; color:{TEXT_MAIN};")
        root.addWidget(lbl_valor)

        # Vencimento + badge
        mid = QHBoxLayout()
        venc_idx = next((i for i, h in enumerate(cabecalho) if "venc" in h.lower()), -1)
        venc = dados[venc_idx] if venc_idx != -1 and venc_idx < len(dados) else ""
        if venc:
            lbl_venc = QLabel(f"Venc. {venc}")
            lbl_venc.setStyleSheet(f"font-size:12px; color:{TEXT_GRAY};")
            mid.addWidget(lbl_venc)
        mid.addStretch()
        badge = QLabel("EM ABERTO")
        badge.setStyleSheet(
            f"background:#fee2e2; color:{WARNING}; border:1px solid #fca5a5;"
            f"border-radius:10px; padding:2px 10px; font-size:10px; font-weight:700;"
        )
        mid.addWidget(badge)
        root.addLayout(mid)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background:{BORDER}; border:none;")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        # Botões de ação
        btns = QHBoxLayout()
        btns.setSpacing(8)
        tem_pix    = bool(pag.get("codcliente") and pag.get("codcobranca"))
        tem_boleto = bool(pag.get("boleto_key"))

        if tem_pix:
            btn_pix = QPushButton("Pagar com Pix")
            btn_pix.setFixedHeight(34)
            btn_pix.setStyleSheet(f"""
                QPushButton {{
                    background:{UNI_BLUE}; color:white;
                    border:none; border-radius:7px;
                    font-size:12px; font-weight:600; padding:0 14px;
                }}
                QPushButton:hover {{ background:{UNI_BLUE2}; }}
            """)
            cc = pag["codcliente"]
            cb = pag["codcobranca"]
            btn_pix.clicked.connect(lambda _, c=cc, b=cb: self.pix_clicked.emit(c, b))
            btns.addWidget(btn_pix)

        if tem_boleto:
            btn_boleto = QPushButton("Ver Boleto")
            btn_boleto.setFixedHeight(34)
            btn_boleto.setStyleSheet(f"""
                QPushButton {{
                    background:white; color:{UNI_BLUE};
                    border:1.5px solid {UNI_BLUE}; border-radius:7px;
                    font-size:12px; font-weight:600; padding:0 14px;
                }}
                QPushButton:hover {{ background:{BG}; }}
            """)
            btn_boleto.clicked.connect(lambda _, p=pag: self.boleto_clicked.emit(p))
            btns.addWidget(btn_boleto)

        btns.addStretch()
        root.addLayout(btns)


# ──────────────────────────────────────────────────────────────
# Janela principal
# ──────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Unifique — Central do Assinante")
        self.setMinimumSize(920, 580)
        self.resize(1060, 680)
        self._dados_cb = None
        self._thread = None
        self._pix_thread = None
        self._setup_ui()
        QTimer.singleShot(300, self._buscar)

    def _setup_ui(self):
        raiz = QWidget()
        self.setCentralWidget(raiz)
        layout = QHBoxLayout(raiz)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Sidebar ─────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setFixedWidth(230)
        sidebar.setStyleSheet(f"background:{UNI_BLUE};")
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(0)

        # Logo
        logo_area = QWidget()
        logo_area.setFixedHeight(72)
        logo_area.setStyleSheet(f"background:{UNI_BLUE};")
        logo_l = QHBoxLayout(logo_area)
        logo_l.setContentsMargins(18, 0, 18, 0)
        logo_l.setSpacing(12)

        icon_box = QLabel("U")
        icon_box.setFixedSize(38, 38)
        icon_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_box.setStyleSheet(f"""
            background:{UNI_ACCENT}; color:white;
            font-size:18px; font-weight:700; border-radius:8px;
        """)

        lbl_logo = QLabel("Unifique")
        lbl_logo.setStyleSheet("color:white; font-size:15px; font-weight:700;")

        logo_l.addWidget(icon_box)
        logo_l.addWidget(lbl_logo)
        logo_l.addStretch()
        side_layout.addWidget(logo_area)

        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet("background:rgba(255,255,255,0.1); border:none;")
        side_layout.addWidget(div)

        side_layout.addSpacing(16)

        lbl_menu = QLabel("Menu")
        lbl_menu.setContentsMargins(20, 0, 0, 0)
        lbl_menu.setStyleSheet(
            "color:rgba(255,255,255,0.35); font-size:10px; font-weight:600; letter-spacing:1px;"
        )
        side_layout.addWidget(lbl_menu)
        side_layout.addSpacing(6)

        self._nav_item(side_layout, "Cobranças em Aberto", ativo=True)
        side_layout.addStretch()

        layout.addWidget(sidebar)

        # ── Área principal ──────────────────────────────────
        main = QWidget()
        main.setStyleSheet(f"background:{BG};")
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Topbar
        topbar = QWidget()
        topbar.setFixedHeight(56)
        topbar.setStyleSheet(f"background:{CARD_BG}; border-bottom:1px solid {BORDER};")
        top_l = QHBoxLayout(topbar)
        top_l.setContentsMargins(20, 0, 20, 0)
        top_l.setSpacing(12)

        btn_toggle = QPushButton("☰")
        btn_toggle.setFixedSize(36, 36)
        btn_toggle.setStyleSheet(f"""
            QPushButton {{
                background:transparent; color:{TEXT_GRAY};
                border:none; font-size:18px; border-radius:6px;
            }}
            QPushButton:hover {{ background:{BG}; }}
        """)
        top_l.addWidget(btn_toggle)

        top_l.addStretch()

        # Botão atualizar — apenas ícone, lado direito
        self.btn_atualizar = QPushButton("↻")
        self.btn_atualizar.setFixedSize(36, 36)
        self.btn_atualizar.setToolTip("Atualizar cobranças")
        self.btn_atualizar.setStyleSheet(f"""
            QPushButton {{
                background:{BG}; color:{UNI_BLUE};
                border:1.5px solid {UNI_BLUE}; border-radius:8px;
                font-size:18px; font-weight:700;
            }}
            QPushButton:hover {{ background:{UNI_BLUE}; color:white; }}
            QPushButton:disabled {{ color:#b0bec5; border-color:{BORDER}; }}
        """)
        self.btn_atualizar.clicked.connect(self._buscar)
        top_l.addWidget(self.btn_atualizar)

        main_layout.addWidget(topbar)

        # Barra de progresso
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(3)
        self.progress.setVisible(False)
        self.progress.setStyleSheet(f"""
            QProgressBar {{ border:none; background:{BORDER}; }}
            QProgressBar::chunk {{ background:{UNI_ACCENT}; }}
        """)
        main_layout.addWidget(self.progress)

        # Scroll
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"border:none; background:{BG};")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setStyleSheet(f"background:{BG};")
        content_l = QVBoxLayout(content)
        content_l.setContentsMargins(28, 28, 28, 28)
        content_l.setSpacing(24)

        # Título da página
        title_w = QWidget()
        title_w.setStyleSheet("background:transparent;")
        tw_l = QVBoxLayout(title_w)
        tw_l.setContentsMargins(0, 0, 0, 0)
        tw_l.setSpacing(2)
        lbl_title = QLabel("Cobranças em Aberto")
        lbl_title.setStyleSheet(f"font-size:22px; font-weight:700; color:{TEXT_MAIN};")
        lbl_subtitle = QLabel("Visão geral das suas cobranças — clique nos cards para pagar")
        lbl_subtitle.setStyleSheet(f"font-size:13px; color:{TEXT_GRAY};")
        tw_l.addWidget(lbl_title)
        tw_l.addWidget(lbl_subtitle)
        content_l.addWidget(title_w)

        # Stat cards
        stat_row = QHBoxLayout()
        stat_row.setSpacing(16)
        self.stat_qtd   = StatCard("Cobranças em Aberto", "—", UNI_ACCENT)
        self.stat_total = StatCard("Total em Aberto",     "—", WARNING)
        stat_row.addWidget(self.stat_qtd)
        stat_row.addWidget(self.stat_total)
        stat_row.addStretch()
        content_l.addLayout(stat_row)

        # Grid de cards de cobrança
        self.cards_outer = QWidget()
        self.cards_outer.setStyleSheet("background:transparent;")
        self.cards_layout = QGridLayout(self.cards_outer)
        self.cards_layout.setSpacing(16)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        content_l.addWidget(self.cards_outer)

        content_l.addStretch()
        scroll.setWidget(content)
        main_layout.addWidget(scroll, 1)

        # Status bar
        self.status = QStatusBar()
        self.status.setStyleSheet(
            f"background:{CARD_BG}; color:{TEXT_GRAY}; border-top:1px solid {BORDER}; font-size:12px;"
        )
        self.setStatusBar(self.status)

        layout.addWidget(main, 1)

    def _nav_item(self, layout, texto: str, ativo=False):
        btn = QWidget()
        btn.setFixedHeight(46)
        btn.setStyleSheet(f"""
            QWidget {{
                background:{'rgba(255,255,255,0.12)' if ativo else 'transparent'};
                border-left: 3px solid {'white' if ativo else 'transparent'};
            }}
        """)
        row = QHBoxLayout(btn)
        row.setContentsMargins(20, 0, 20, 0)
        row.setSpacing(12)
        lbl_tx = QLabel(texto)
        lbl_tx.setStyleSheet(
            f"color:{'white' if ativo else 'rgba(255,255,255,0.65)'}; "
            f"font-size:13px; font-weight:{'600' if ativo else '400'}; border:none; background:transparent;"
        )
        row.addWidget(lbl_tx)
        row.addStretch()
        layout.addWidget(btn)

    # ── Lógica ──────────────────────────────────────────────

    def _buscar(self):
        cpf   = os.getenv("UNIFIQUE_CPF", "").strip()
        senha = os.getenv("UNIFIQUE_SENHA", "").strip()
        if not cpf or not senha:
            QMessageBox.critical(self, "Credenciais ausentes",
                                 "Defina UNIFIQUE_CPF e UNIFIQUE_SENHA no arquivo .env")
            return

        self.btn_atualizar.setEnabled(False)
        self.progress.setVisible(True)
        self.status.showMessage("Conectando ao portal Unifique...")
        self._limpar_cards()

        self._thread = BuscaThread(cpf, senha)
        self._thread.concluido.connect(self._on_concluido)
        self._thread.erro.connect(self._on_erro)
        self._thread.start()

    def _limpar_cards(self):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.stat_qtd.set_valor("—")
        self.stat_total.set_valor("—")

    def _on_concluido(self, cabecalho, dados, pagamentos):
        self.progress.setVisible(False)
        self.btn_atualizar.setEnabled(True)
        self._dados_cb = (cabecalho, dados)

        if not dados:
            lbl = QLabel("Nenhuma cobrança em aberto ✓")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"font-size:15px; color:{SUCCESS}; padding:40px;")
            self.cards_layout.addWidget(lbl, 0, 0, 1, 2)
            self.stat_qtd.set_valor("0")
            self.stat_total.set_valor("R$ 0,00")
            self.status.showMessage("Sem cobranças em aberto.")
            return

        val_idx = next((i for i, h in enumerate(cabecalho) if "valor" in h.lower()), -1)
        total = 0.0

        for i, (linha, pag) in enumerate(zip(dados, pagamentos)):
            card = CobrancaCard(linha, cabecalho, pag)
            card.pix_clicked.connect(self._abrir_pix)
            card.boleto_clicked.connect(self._abrir_boleto)
            self.cards_layout.addWidget(card, i // 2, i % 2)

            if val_idx != -1 and val_idx < len(linha):
                try:
                    raw = linha[val_idx].replace("R$", "").replace(".", "").replace(",", ".").strip()
                    total += float(raw)
                except Exception:
                    pass

        self.stat_qtd.set_valor(str(len(dados)))
        total_fmt = f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        self.stat_total.set_valor(total_fmt)

        qtd = len(dados)
        self.status.showMessage(f"  {qtd} cobrança{'s' if qtd != 1 else ''} em aberto encontrada{'s' if qtd != 1 else ''}.")

    def _on_erro(self, msg):
        self.progress.setVisible(False)
        self.btn_atualizar.setEnabled(True)
        self.status.showMessage(f"Erro: {msg}")
        QMessageBox.critical(self, "Erro", msg)

    def _abrir_pix(self, codcliente: int, codcobranca: int):
        self.progress.setVisible(True)
        self.status.showMessage("Buscando código Pix...")
        self._pix_thread = PixThread(codcliente, codcobranca)
        self._pix_thread.concluido.connect(self._on_pix)
        self._pix_thread.erro.connect(lambda m: (
            self.progress.setVisible(False),
            self.status.showMessage(f"Erro: {m}"),
            QMessageBox.critical(self, "Erro", m),
        ))
        self._pix_thread.start()

    def _on_pix(self, resultado: dict):
        self.progress.setVisible(False)
        self.status.showMessage("Pronto.")
        code = resultado.get("pix_code")
        if not code:
            QMessageBox.warning(self, "Pix indisponível",
                                "Não foi possível obter o código Pix desta cobrança.")
            return
        dlg = PixDialog(code, resultado, self)
        dlg.exec()

    def _abrir_boleto(self, pag: dict):
        key = pag.get("boleto_key", "")
        if not key:
            QMessageBox.warning(self, "Boleto", "Chave do boleto não encontrada.")
            return
        url = fetcher.get_boleto_url(key)
        cpf   = os.getenv("UNIFIQUE_CPF", "").strip()
        senha = os.getenv("UNIFIQUE_SENHA", "").strip()
        dlg = BoletoDialog(url, cpf, senha, self)
        dlg.exec()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Unifique Central")
    app.setStyle("Fusion")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
