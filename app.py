import os
import sys
import csv
import webbrowser
from io import BytesIO
from dotenv import load_dotenv

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QScrollArea, QSizePolicy,
    QFileDialog, QMessageBox, QDialog, QLineEdit, QProgressBar,
    QStatusBar, QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize, QUrl
from PyQt6.QtGui import QFont, QColor, QPixmap, QAction, QKeySequence, QPainter, QBrush, QPen
from PyQt6.QtWebEngineWidgets import QWebEngineView

load_dotenv()
import fetcher

# ── Paleta Unifique ──────────────────────────────────────────
UNI_BLUE   = "#253A76"   # azul principal
UNI_BLUE2  = "#1a2d5e"   # hover
UNI_ACCENT = "#0091d5"   # azul claro de destaque
BG         = "#f4f6fb"   # fundo geral
CARD_BG    = "#ffffff"
TEXT_MAIN  = "#1a1a2e"
TEXT_GRAY  = "#6b7280"
SUCCESS    = "#16a34a"
WARNING    = "#dc2626"
BORDER     = "#e5e7eb"


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

        # Cabeçalho
        hdr = QHBoxLayout()
        dot = QLabel("●")
        dot.setStyleSheet(f"color:{UNI_ACCENT}; font-size:20px;")
        title = QLabel("Pagar com Pix")
        title.setStyleSheet(f"font-size:18px; font-weight:700; color:{TEXT_MAIN};")
        hdr.addWidget(dot)
        hdr.addWidget(title)
        hdr.addStretch()
        root.addLayout(hdr)

        # Valor
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

        # QR Code
        qr_lbl = QLabel()
        qr_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        px = gerar_qr_pixmap(pix_code)
        if px:
            qr_lbl.setPixmap(px)
        else:
            qr_lbl.setText("QR Code indisponível")
        root.addWidget(qr_lbl)

        # Pix copia e cola
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
            f"QPushButton:hover {{background:{UNI_BLUE2};}}"
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
# Diálogo Boleto — auto-login no WebEngine, navega ao boleto
# ──────────────────────────────────────────────────────────────
class BoletoDialog(QDialog):
    _LOGIN_URL  = "https://servicos.unifique.com.br/login/in/Lw=="
    _PORTAL_URL = "https://servicos.unifique.com.br"

    def __init__(self, boleto_url: str, cpf: str, senha: str, parent=None):
        super().__init__(parent)
        self._boleto_url = boleto_url
        self._cpf  = cpf.replace("'", "")
        self._senha = senha.replace("'", "")
        self._logged = False

        self.setWindowTitle("Boleto — Unifique")
        self.resize(940, 680)
        self.setStyleSheet(f"background:{CARD_BG};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Barra superior
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
            # Preenche e submete o login via JS
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
            # Login concluído — navega ao boleto
            self._logged = True
            self._lbl_status.setText("Carregando boleto…")
            self._view.load(QUrl(self._boleto_url))

        elif self._logged:
            self._lbl_status.setText("Boleto")


# ──────────────────────────────────────────────────────────────
# Card de cobrança
# ──────────────────────────────────────────────────────────────
class CobrancaCard(QFrame):
    pix_clicked    = pyqtSignal(int, int)   # codcliente, codcobranca
    boleto_clicked = pyqtSignal(object)     # pag dict

    def __init__(self, dados: list, cabecalho: list, pag: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setStyleSheet(f"""
            QFrame#card {{
                background:{CARD_BG};
                border:1px solid {BORDER};
                border-radius:12px;
            }}
        """)
        sombra = QGraphicsDropShadowEffect()
        sombra.setBlurRadius(16)
        sombra.setOffset(0, 2)
        sombra.setColor(QColor(0, 0, 0, 25))
        self.setGraphicsEffect(sombra)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        # Linha superior: descrição + valor
        top = QHBoxLayout()

        # Ícone boleto
        icone = QLabel("🧾")
        icone.setStyleSheet("font-size:22px;")
        icone.setFixedWidth(34)

        # Descrição e vencimento
        info_col = QVBoxLayout()
        info_col.setSpacing(2)

        desc_idx = next((i for i, h in enumerate(cabecalho) if "desc" in h.lower()), 0)
        desc = dados[desc_idx] if desc_idx < len(dados) else dados[0] if dados else "Cobrança"
        # Simplifica: pega só até o primeiro "(" ou quebra de linha
        desc_curta = desc.split("(")[0].strip()

        lbl_desc = QLabel(desc_curta)
        lbl_desc.setStyleSheet(f"font-size:14px; font-weight:600; color:{TEXT_MAIN};")
        lbl_desc.setWordWrap(True)

        venc_idx = next((i for i, h in enumerate(cabecalho) if "venc" in h.lower()), -1)
        venc = dados[venc_idx] if venc_idx != -1 and venc_idx < len(dados) else ""
        lbl_venc = QLabel(f"Vencimento: {venc}" if venc else "")
        lbl_venc.setStyleSheet(f"font-size:12px; color:{TEXT_GRAY};")

        info_col.addWidget(lbl_desc)
        info_col.addWidget(lbl_venc)

        top.addWidget(icone)
        top.addLayout(info_col, 1)

        # Valor
        val_idx = next((i for i, h in enumerate(cabecalho) if "valor" in h.lower()), -1)
        valor_txt = dados[val_idx] if val_idx != -1 and val_idx < len(dados) else ""
        lbl_valor = QLabel(valor_txt)
        lbl_valor.setStyleSheet(f"font-size:20px; font-weight:700; color:{UNI_BLUE};")
        lbl_valor.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(lbl_valor)

        root.addLayout(top)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{BORDER};")
        root.addWidget(sep)

        # Botões
        btns = QHBoxLayout()
        btns.setSpacing(10)

        tem_pix = bool(pag.get("codcliente") and pag.get("codcobranca"))
        tem_boleto = bool(pag.get("boleto_key"))

        if tem_pix:
            btn_pix = QPushButton("Pagar com Pix")
            btn_pix.setFixedHeight(36)
            btn_pix.setStyleSheet(f"""
                QPushButton {{
                    background:{UNI_BLUE}; color:white;
                    border:none; border-radius:8px;
                    font-size:13px; font-weight:600; padding:0 16px;
                }}
                QPushButton:hover {{ background:{UNI_BLUE2}; }}
            """)
            cc = pag["codcliente"]
            cb = pag["codcobranca"]
            btn_pix.clicked.connect(lambda _, c=cc, b=cb: self.pix_clicked.emit(c, b))
            btns.addWidget(btn_pix)

        if tem_boleto:
            btn_boleto = QPushButton("Ver Boleto")
            btn_boleto.setFixedHeight(36)
            btn_boleto.setStyleSheet(f"""
                QPushButton {{
                    background:white; color:{UNI_BLUE};
                    border:2px solid {UNI_BLUE}; border-radius:8px;
                    font-size:13px; font-weight:600; padding:0 16px;
                }}
                QPushButton:hover {{ background:{BG}; }}
            """)
            btn_boleto.clicked.connect(lambda _, p=pag: self.boleto_clicked.emit(p))
            btns.addWidget(btn_boleto)

        btns.addStretch()

        # Badge status
        badge = QLabel("EM ABERTO")
        badge.setStyleSheet(
            f"background:#fef2f2; color:{WARNING}; border:1px solid #fecaca;"
            f"border-radius:12px; padding:3px 10px; font-size:11px; font-weight:700;"
        )
        btns.addWidget(badge)

        root.addLayout(btns)


# ──────────────────────────────────────────────────────────────
# Janela principal
# ──────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Unifique — Central do Assinante")
        self.setMinimumSize(860, 540)
        self.resize(980, 620)
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
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(f"background:{UNI_BLUE};")
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(0)

        # Logo / marca
        logo_area = QWidget()
        logo_area.setFixedHeight(80)
        logo_area.setStyleSheet(f"background:{UNI_BLUE2};")
        logo_l = QVBoxLayout(logo_area)
        logo_l.setContentsMargins(20, 0, 20, 0)
        lbl_logo = QLabel("unifique")
        lbl_logo.setStyleSheet(
            "color:white; font-size:22px; font-weight:700; letter-spacing:2px;"
        )
        lbl_logo.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lbl_sub = QLabel("Central do Assinante")
        lbl_sub.setStyleSheet("color:rgba(255,255,255,0.55); font-size:10px; letter-spacing:1px;")
        logo_l.addWidget(lbl_logo)
        logo_l.addWidget(lbl_sub)
        side_layout.addWidget(logo_area)

        side_layout.addSpacing(16)

        # Itens de menu
        self._nav_item(side_layout, "💳", "Cobranças em Aberto", ativo=True)
        side_layout.addStretch()

        # Rodapé sidebar
        rodape = QLabel("v1.0")
        rodape.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rodape.setStyleSheet("color:rgba(255,255,255,0.3); font-size:10px; padding:12px;")
        side_layout.addWidget(rodape)

        layout.addWidget(sidebar)

        # ── Área principal ──────────────────────────────────
        main = QWidget()
        main.setStyleSheet(f"background:{BG};")
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Topbar
        topbar = QWidget()
        topbar.setFixedHeight(64)
        topbar.setStyleSheet(f"background:{CARD_BG}; border-bottom:1px solid {BORDER};")
        top_l = QHBoxLayout(topbar)
        top_l.setContentsMargins(28, 0, 28, 0)

        lbl_pagina = QLabel("Cobranças em Aberto")
        lbl_pagina.setStyleSheet(f"font-size:16px; font-weight:600; color:{TEXT_MAIN};")

        self.btn_atualizar = QPushButton("↻  Atualizar")
        self.btn_atualizar.setFixedHeight(36)
        self.btn_atualizar.setFixedWidth(120)
        self.btn_atualizar.setStyleSheet(f"""
            QPushButton {{
                background:{BG}; color:{UNI_BLUE};
                border:1.5px solid {UNI_BLUE}; border-radius:8px;
                font-size:13px; font-weight:600;
            }}
            QPushButton:hover {{ background:{UNI_BLUE}; color:white; }}
            QPushButton:disabled {{ color:#aaa; border-color:#ddd; }}
        """)
        self.btn_atualizar.clicked.connect(self._buscar)

        self.btn_exportar = QPushButton("⬇  Exportar")
        self.btn_exportar.setFixedHeight(36)
        self.btn_exportar.setFixedWidth(110)
        self.btn_exportar.setEnabled(False)
        self.btn_exportar.setStyleSheet(f"""
            QPushButton {{
                background:{BG}; color:{TEXT_GRAY};
                border:1.5px solid {BORDER}; border-radius:8px;
                font-size:13px;
            }}
            QPushButton:hover {{ background:{BORDER}; }}
            QPushButton:disabled {{ color:#ccc; border-color:#eee; }}
        """)
        self.btn_exportar.clicked.connect(self._exportar_csv)

        top_l.addWidget(lbl_pagina)
        top_l.addStretch()
        top_l.addWidget(self.btn_atualizar)
        top_l.addSpacing(8)
        top_l.addWidget(self.btn_exportar)
        main_layout.addWidget(topbar)

        # Loading bar (fina, embaixo do topbar)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(3)
        self.progress.setVisible(False)
        self.progress.setStyleSheet(f"""
            QProgressBar {{ border:none; background:{BORDER}; }}
            QProgressBar::chunk {{ background:{UNI_ACCENT}; }}
        """)
        main_layout.addWidget(self.progress)

        # Scroll com cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"border:none; background:{BG};")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.cards_container = QWidget()
        self.cards_container.setStyleSheet(f"background:{BG};")
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(28, 24, 28, 24)
        self.cards_layout.setSpacing(14)
        self.cards_layout.addStretch()

        scroll.setWidget(self.cards_container)
        main_layout.addWidget(scroll, 1)

        # Status bar
        self.status = QStatusBar()
        self.status.setStyleSheet(
            f"background:{CARD_BG}; color:{TEXT_GRAY}; border-top:1px solid {BORDER}; font-size:12px;"
        )
        self.setStatusBar(self.status)

        layout.addWidget(main, 1)

        # Menu
        menu = self.menuBar()
        menu.setStyleSheet(
            f"background:{CARD_BG}; color:{TEXT_MAIN}; border-bottom:1px solid {BORDER};"
        )
        m_arq = menu.addMenu("Arquivo")
        for txt, sc, fn in [("Atualizar", "F5", self._buscar),
                             ("Exportar CSV...", "", self._exportar_csv)]:
            a = QAction(txt, self)
            if sc:
                a.setShortcut(QKeySequence(sc))
            a.triggered.connect(fn)
            m_arq.addAction(a)
        m_arq.addSeparator()
        s = QAction("Sair", self); s.triggered.connect(self.close); m_arq.addAction(s)

    def _nav_item(self, layout, icon: str, texto: str, ativo=False):
        btn = QWidget()
        btn.setFixedHeight(46)
        cor_bg = "rgba(255,255,255,0.12)" if ativo else "transparent"
        btn.setStyleSheet(f"""
            QWidget {{ background:{cor_bg}; border-left: 3px solid {'white' if ativo else 'transparent'}; }}
        """)
        row = QHBoxLayout(btn)
        row.setContentsMargins(20, 0, 20, 0)
        row.setSpacing(12)
        lbl_ic = QLabel(icon)
        lbl_ic.setStyleSheet("font-size:16px; border:none; background:transparent;")
        lbl_tx = QLabel(texto)
        lbl_tx.setStyleSheet(
            f"color:{'white' if ativo else 'rgba(255,255,255,0.65)'}; "
            f"font-size:13px; font-weight:{'600' if ativo else '400'}; border:none; background:transparent;"
        )
        row.addWidget(lbl_ic)
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
        self.btn_exportar.setEnabled(False)
        self.progress.setVisible(True)
        self.status.showMessage("Conectando ao portal Unifique...")
        self._limpar_cards()

        self._thread = BuscaThread(cpf, senha)
        self._thread.concluido.connect(self._on_concluido)
        self._thread.erro.connect(self._on_erro)
        self._thread.start()

    def _limpar_cards(self):
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_concluido(self, cabecalho, dados, pagamentos):
        self.progress.setVisible(False)
        self.btn_atualizar.setEnabled(True)
        self._dados_cb = (cabecalho, dados)

        if not dados:
            lbl = QLabel("Nenhuma cobrança em aberto. ✓")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"font-size:15px; color:{SUCCESS}; padding:40px;")
            self.cards_layout.insertWidget(0, lbl)
            self.status.showMessage("Sem cobranças em aberto.")
            return

        for i, (linha, pag) in enumerate(zip(dados, pagamentos)):
            card = CobrancaCard(linha, cabecalho, pag)
            card.pix_clicked.connect(self._abrir_pix)
            card.boleto_clicked.connect(self._abrir_boleto)
            self.cards_layout.insertWidget(i, card)

        self.btn_exportar.setEnabled(True)
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

    def _exportar_csv(self):
        if not self._dados_cb:
            return
        cab, dados = self._dados_cb
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar CSV", "cobrancas_unifique.csv", "CSV (*.csv)")
        if not caminho:
            return
        with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(cab)
            w.writerows(dados)
        self.status.showMessage(f"Exportado: {caminho}")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Unifique Central")
    app.setStyle("Fusion")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
