import os
import sys
import urllib.parse
from io import BytesIO
from datetime import datetime, date
from dotenv import load_dotenv

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QScrollArea,
    QMessageBox, QDialog, QLineEdit, QProgressBar,
    QStatusBar, QGridLayout, QComboBox, QSystemTrayIcon, QMenu, QFileDialog,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QUrl
from PyQt6.QtGui import QPixmap, QIcon, QAction, QDesktopServices, QColor, QPainter, QBrush
from PyQt6.QtWebEngineWidgets import QWebEngineView

load_dotenv()
import fetcher

# ── Palette ───────────────────────────────────────────────────
UNI_BLUE   = "#253A76"
UNI_BLUE2  = "#1a2d5e"
UNI_ACCENT = "#0ea5e9"
BG         = "#eef2ff"
CARD_BG    = "#ffffff"
TEXT_MAIN  = "#0f172a"
TEXT_GRAY  = "#64748b"
SUCCESS    = "#22c55e"
WARNING    = "#ef4444"
ORANGE     = "#f97316"
BORDER     = "#dde3f0"

# ── Optional deps ─────────────────────────────────────────────
try:
    import matplotlib
    matplotlib.use("QtAgg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

try:
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.styles import ParagraphStyle
    HAS_RL = True
except ImportError:
    HAS_RL = False


# ── Helpers ───────────────────────────────────────────────────
def _parse_venc(s: str) -> date | None:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            pass
    return None


def _dias_venc(s: str) -> int | None:
    d = _parse_venc(s)
    return None if d is None else (d - date.today()).days


def _parse_valor(s: str) -> float:
    try:
        return float(s.replace("R$", "").replace(".", "").replace(",", ".").strip())
    except Exception:
        return 0.0


def _fazer_icon() -> QIcon:
    px = QPixmap(32, 32)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QBrush(QColor(UNI_BLUE)))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(0, 0, 32, 32, 6, 6)
    p.setPen(QColor("white"))
    f = p.font()
    f.setPixelSize(16)
    f.setBold(True)
    p.setFont(f)
    p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "U")
    p.end()
    return QIcon(px)


def _gerar_pdf(cabecalho: list, dados: list, filepath: str) -> tuple[bool, str]:
    if not HAS_RL:
        return False, "reportlab nao instalado.\nExecute: pip install reportlab"
    try:
        doc = SimpleDocTemplate(filepath, pagesize=A4,
                                rightMargin=25, leftMargin=25,
                                topMargin=25, bottomMargin=25)
        title_s = ParagraphStyle("t", fontSize=18, fontName="Helvetica-Bold",
                                 textColor=rl_colors.HexColor(UNI_BLUE), spaceAfter=4)
        sub_s   = ParagraphStyle("s", fontSize=10,
                                 textColor=rl_colors.HexColor(TEXT_GRAY), spaceAfter=18)
        story = [
            Paragraph("Unifique - Cobranças em Aberto", title_s),
            Paragraph(f"Gerado em {datetime.now().strftime('%d/%m/%Y as %H:%M')}", sub_s),
        ]
        skip     = {"acoes", "acao", "ações", ""}
        col_idx  = [i for i, h in enumerate(cabecalho) if h.lower() not in skip]
        col_hdrs = [cabecalho[i] for i in col_idx]
        table_data = [col_hdrs]
        for linha in dados:
            table_data.append([linha[i] if i < len(linha) else "" for i in col_idx])
        n = len(col_hdrs) or 1
        col_w = [(A4[0] - 50) / n] * n
        tbl = Table(table_data, colWidths=col_w, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND",     (0, 0), (-1, 0),  rl_colors.HexColor(UNI_BLUE)),
            ("TEXTCOLOR",      (0, 0), (-1, 0),  rl_colors.white),
            ("FONTNAME",       (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",       (0, 0), (-1, 0),  9),
            ("FONTSIZE",       (0, 1), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [rl_colors.white, rl_colors.HexColor(BG)]),
            ("GRID",           (0, 0), (-1, -1), 0.5, rl_colors.HexColor(BORDER)),
            ("LEFTPADDING",    (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",   (0, 0), (-1, -1), 6),
            ("TOPPADDING",     (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
        ]))
        story.append(tbl)
        doc.build(story)
        return True, filepath
    except Exception as e:
        return False, str(e)


# ── Threads ───────────────────────────────────────────────────
class BuscaThread(QThread):
    concluido = pyqtSignal(list, list, list)
    erro = pyqtSignal(str)

    def __init__(self, cpf, senha):
        super().__init__()
        self.cpf = cpf
        self.senha = senha

    def run(self):
        try:
            self.concluido.emit(*fetcher.buscar_cobrancas_completo(self.cpf, self.senha))
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


# ── QR Code ───────────────────────────────────────────────────
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


# ── Pix Dialog ────────────────────────────────────────────────
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
        hdr.addWidget(dot); hdr.addWidget(title); hdr.addStretch()
        root.addLayout(hdr)

        valor = info.get("valor_original", 0) or 0
        juros = info.get("juros_multa", 0) or 0
        dias  = info.get("dias_atraso", 0) or 0

        val_box = QFrame()
        val_box.setStyleSheet(f"background:{BG}; border-radius:10px; border:1px solid {BORDER};")
        vl = QVBoxLayout(val_box)
        vl.setContentsMargins(16, 12, 16, 12)
        lbl_total = QLabel(f"R$ {valor:.2f}".replace(".", ","))
        lbl_total.setStyleSheet(f"font-size:28px; font-weight:700; color:{UNI_BLUE};")
        lbl_total.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(lbl_total)
        if dias > 0:
            lbl_j = QLabel(f"⚠ {dias} dias em atraso · Juros/multa: R$ {juros:.2f}".replace(".", ","))
            lbl_j.setStyleSheet(f"font-size:11px; color:{WARNING}; font-weight:500;")
            lbl_j.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vl.addWidget(lbl_j)
        root.addWidget(val_box)

        qr_lbl = QLabel()
        qr_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        px = gerar_qr_pixmap(pix_code)
        qr_lbl.setPixmap(px) if px else qr_lbl.setText("QR Code indisponivel")
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
        btn_cop = QPushButton("Copiar")
        btn_cop.setFixedSize(72, 36)
        btn_cop.setStyleSheet(
            f"background:{UNI_BLUE}; color:white; border:none; border-radius:8px;"
            f"font-size:12px; font-weight:600;"
        )
        btn_cop.clicked.connect(self._copiar)
        row_pix.addWidget(self.campo_pix); row_pix.addWidget(btn_cop)
        root.addLayout(row_pix)

        btn_f = QPushButton("Fechar")
        btn_f.setFixedHeight(40)
        btn_f.setStyleSheet(
            f"background:{BG}; color:{TEXT_GRAY}; border:1px solid {BORDER};"
            f"border-radius:8px; font-size:13px;"
        )
        btn_f.clicked.connect(self.accept)
        root.addWidget(btn_f)

    def _copiar(self):
        QApplication.clipboard().setText(self.campo_pix.text())
        QMessageBox.information(self, "Copiado!", "Codigo Pix copiado.")


# ── Boleto Dialog ─────────────────────────────────────────────
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
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 0, 16, 0)
        self._lbl_st = QLabel("Conectando ao portal…")
        self._lbl_st.setStyleSheet("color:white; font-size:13px; font-weight:600;")
        btn_f = QPushButton("✕  Fechar")
        btn_f.setFixedHeight(32)
        btn_f.setStyleSheet(
            "background:rgba(255,255,255,0.15); color:white; border:none;"
            "border-radius:6px; padding:0 12px; font-size:12px;"
        )
        btn_f.clicked.connect(self.accept)
        bl.addWidget(self._lbl_st); bl.addStretch(); bl.addWidget(btn_f)
        root.addWidget(bar)

        self._view = QWebEngineView()
        self._view.loadFinished.connect(self._on_load)
        self._view.load(QUrl(self._LOGIN_URL))
        root.addWidget(self._view, 1)

    def _on_load(self, ok: bool):
        url = self._view.url().toString()
        if not self._logged and ("login" in url or url == self._LOGIN_URL):
            self._lbl_st.setText("Autenticando…")
            js = f"""(function(){{
                var cpf=document.querySelector('[name="login_cpfcnpj"]');
                var pwd=document.querySelector('[name="login_senha"]');
                var form=document.querySelector('form');
                if(cpf&&pwd&&form){{cpf.value='{self._cpf}';pwd.value='{self._senha}';form.submit();}}
            }})();"""
            self._view.page().runJavaScript(js)
        elif not self._logged and "login" not in url:
            self._logged = True
            self._lbl_st.setText("Carregando boleto…")
            self._view.load(QUrl(self._boleto_url))
        elif self._logged:
            self._lbl_st.setText("Boleto")


# ── Stat Card ─────────────────────────────────────────────────
class StatCard(QFrame):
    def __init__(self, titulo: str, valor: str, accent: str, parent=None):
        super().__init__(parent)
        self.setObjectName("sc")
        self.setMinimumWidth(180)
        self.setFixedHeight(110)
        self.setStyleSheet(f"""
            QFrame#sc {{
                background:{CARD_BG}; border:1px solid {BORDER};
                border-top:3px solid {accent}; border-radius:12px;
            }}
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 14)
        root.setSpacing(8)
        lbl_t = QLabel(titulo)
        lbl_t.setStyleSheet(f"font-size:13px; color:{TEXT_GRAY};")
        root.addWidget(lbl_t)
        self.lbl_v = QLabel(valor)
        self.lbl_v.setStyleSheet(f"font-size:26px; font-weight:700; color:{TEXT_MAIN};")
        root.addWidget(self.lbl_v)

    def set_valor(self, v: str):
        self.lbl_v.setText(v)


# ── Filter Bar ────────────────────────────────────────────────
class FilterBar(QFrame):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("fb")
        self.setStyleSheet(f"QFrame#fb {{ background:{CARD_BG}; border:1px solid {BORDER}; border-radius:10px; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(12)

        self.txt = QLineEdit()
        self.txt.setPlaceholderText("Buscar por descricao, CPF ou nome...")
        self.txt.setStyleSheet(f"""
            QLineEdit {{
                background:{BG}; border:1px solid {BORDER}; border-radius:7px;
                padding:6px 12px; font-size:13px; color:{TEXT_MAIN};
            }}
        """)
        self.txt.textChanged.connect(self.changed)
        lay.addWidget(self.txt, 2)

        lay.addWidget(self._vsep())

        lbl_v = QLabel("Vencimento:")
        lbl_v.setStyleSheet(f"color:{TEXT_GRAY}; font-size:12px; background:transparent;")
        lay.addWidget(lbl_v)

        self.cmb_venc = QComboBox()
        self.cmb_venc.addItems(["Todos", "Hoje", "Esta semana", "Este mes", "Vencidos"])
        self._estilo_cmb(self.cmb_venc)
        self.cmb_venc.currentIndexChanged.connect(self.changed)
        lay.addWidget(self.cmb_venc)

        lay.addWidget(self._vsep())

        lbl_s = QLabel("Ordenar:")
        lbl_s.setStyleSheet(f"color:{TEXT_GRAY}; font-size:12px; background:transparent;")
        lay.addWidget(lbl_s)

        self.cmb_sort = QComboBox()
        self.cmb_sort.addItems(["Padrao", "Valor crescente", "Valor decrescente", "Venc. proximo", "Venc. distante"])
        self._estilo_cmb(self.cmb_sort)
        self.cmb_sort.currentIndexChanged.connect(self.changed)
        lay.addWidget(self.cmb_sort)

    def _vsep(self):
        f = QFrame()
        f.setFrameShape(QFrame.Shape.VLine)
        f.setFixedSize(1, 24)
        f.setStyleSheet(f"background:{BORDER}; border:none;")
        return f

    def _estilo_cmb(self, c: QComboBox):
        c.setStyleSheet(f"""
            QComboBox {{
                background:{BG}; border:1px solid {BORDER}; border-radius:7px;
                padding:5px 10px; font-size:12px; color:{TEXT_MAIN}; min-width:130px;
            }}
            QComboBox::drop-down {{ border:none; width:20px; }}
            QComboBox QAbstractItemView {{
                background:{CARD_BG}; border:1px solid {BORDER};
                selection-background-color:{UNI_ACCENT}; selection-color:white;
            }}
        """)

    @property
    def busca(self) -> str:
        return self.txt.text().lower().strip()

    @property
    def filtro_venc(self) -> str:
        return self.cmb_venc.currentText()

    @property
    def ordenacao(self) -> str:
        return self.cmb_sort.currentText()


# ── Chart Widget ──────────────────────────────────────────────
class ChartWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cw")
        self.setStyleSheet(f"QFrame#cw {{ background:{CARD_BG}; border:1px solid {BORDER}; border-radius:12px; }}")
        self.setMinimumHeight(260)
        self.setMaximumHeight(300)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 14)
        root.setSpacing(8)

        hdr = QHBoxLayout()
        lbl = QLabel("Distribuicao de Cobranças por Valor")
        lbl.setStyleSheet(f"font-size:14px; font-weight:700; color:{TEXT_MAIN}; background:transparent;")
        hdr.addWidget(lbl)
        hdr.addStretch()
        for cor, txt in [(UNI_ACCENT, "Normal"), (ORANGE, "< 7 dias"), (WARNING, "Vencida")]:
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{cor}; font-size:10px; background:transparent;")
            ltxt = QLabel(txt)
            ltxt.setStyleSheet(f"color:{TEXT_GRAY}; font-size:10px; background:transparent;")
            hdr.addWidget(dot)
            hdr.addWidget(ltxt)
            hdr.addSpacing(6)
        root.addLayout(hdr)

        if HAS_MPL:
            self.fig = Figure(facecolor=CARD_BG)
            self.ax  = self.fig.add_subplot(111)
            self.canvas = FigureCanvasQTAgg(self.fig)
            self.canvas.setStyleSheet("background:transparent;")
            root.addWidget(self.canvas, 1)
        else:
            self.canvas = None
            lbl_no = QLabel("pip install matplotlib  para ver o grafico")
            lbl_no.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_no.setStyleSheet(f"color:{TEXT_GRAY}; font-size:12px; background:transparent;")
            root.addWidget(lbl_no)

    def atualizar(self, dados: list, cabecalho: list):
        if not HAS_MPL or self.canvas is None:
            return
        self.ax.clear()
        self.ax.set_facecolor(CARD_BG)
        self.fig.patch.set_facecolor(CARD_BG)

        if not dados:
            self.ax.text(0.5, 0.5, "Sem dados para exibir",
                         ha="center", va="center",
                         transform=self.ax.transAxes, color=TEXT_GRAY, fontsize=11)
            for sp in self.ax.spines.values():
                sp.set_visible(False)
            self.ax.set_xticks([])
            self.ax.set_yticks([])
            self.canvas.draw()
            return

        val_idx  = next((i for i, h in enumerate(cabecalho) if "valor" in h.lower()), -1)
        venc_idx = next((i for i, h in enumerate(cabecalho) if "venc"  in h.lower()), -1)
        desc_idx = next((i for i, h in enumerate(cabecalho) if "desc"  in h.lower()), 0)

        labels, values, bar_cols = [], [], []
        for i, linha in enumerate(dados):
            d = linha[desc_idx] if desc_idx < len(linha) else f"#{i+1}"
            labels.append(d.split("(")[0].strip()[:18])
            val = _parse_valor(linha[val_idx]) if val_idx != -1 and val_idx < len(linha) else 0.0
            values.append(val)
            venc = linha[venc_idx] if venc_idx != -1 and venc_idx < len(linha) else ""
            dias = _dias_venc(venc)
            if dias is not None and dias < 0:
                bar_cols.append("#ef4444")
            elif dias is not None and dias <= 7:
                bar_cols.append("#f97316")
            else:
                bar_cols.append("#0ea5e9")

        x = list(range(len(labels)))
        bars = self.ax.bar(x, values, color=bar_cols, width=0.55, zorder=2)
        self.ax.set_xticks(x)
        self.ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=7.5, color=TEXT_GRAY)
        self.ax.set_ylabel("R$", fontsize=9, color=TEXT_GRAY)
        self.ax.tick_params(axis="y", colors=TEXT_GRAY, labelsize=8)
        self.ax.tick_params(axis="x", colors=TEXT_GRAY)
        for sp in self.ax.spines.values():
            sp.set_color(BORDER)
        self.ax.yaxis.grid(True, color=BORDER, linewidth=0.5, zorder=1)
        self.ax.set_axisbelow(True)
        max_v = max(values) if values else 1
        for bar, val in zip(bars, values):
            if val > 0:
                self.ax.text(bar.get_x() + bar.get_width() / 2,
                             bar.get_height() + max_v * 0.02,
                             f"R${val:,.0f}".replace(",", "."),
                             ha="center", va="bottom", fontsize=7, color=TEXT_MAIN)
        self.fig.tight_layout(pad=0.4)
        self.canvas.draw()


# ── Cobrança Card ─────────────────────────────────────────────
class CobrancaCard(QFrame):
    pix_clicked    = pyqtSignal(int, int)
    boleto_clicked = pyqtSignal(object)

    def __init__(self, dados: list, cabecalho: list, pag: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("card")

        venc_idx = next((i for i, h in enumerate(cabecalho) if "venc" in h.lower()), -1)
        venc_str = dados[venc_idx] if venc_idx != -1 and venc_idx < len(dados) else ""
        dias = _dias_venc(venc_str)

        if dias is not None and dias < 0:
            bord = WARNING
        elif dias is not None and dias <= 7:
            bord = ORANGE
        else:
            bord = UNI_ACCENT

        self.setStyleSheet(f"""
            QFrame#card {{
                background:{CARD_BG}; border:1px solid {BORDER};
                border-left:4px solid {bord}; border-radius:12px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        desc_idx = next((i for i, h in enumerate(cabecalho) if "desc" in h.lower()), 0)
        desc = dados[desc_idx] if desc_idx < len(dados) else dados[0] if dados else "Cobrança"
        desc_c = desc.split("(")[0].strip()

        lbl_desc = QLabel(desc_c)
        lbl_desc.setStyleSheet(f"font-size:13px; color:{TEXT_GRAY};")
        lbl_desc.setWordWrap(True)
        root.addWidget(lbl_desc)

        val_idx = next((i for i, h in enumerate(cabecalho) if "valor" in h.lower()), -1)
        valor_txt = dados[val_idx] if val_idx != -1 and val_idx < len(dados) else ""
        lbl_v = QLabel(valor_txt)
        lbl_v.setStyleSheet(f"font-size:26px; font-weight:700; color:{TEXT_MAIN};")
        root.addWidget(lbl_v)

        mid = QHBoxLayout()
        if venc_str:
            lbl_venc = QLabel(f"Venc. {venc_str}")
            lbl_venc.setStyleSheet(f"font-size:12px; color:{TEXT_GRAY};")
            mid.addWidget(lbl_venc)
            if dias is not None:
                if dias < 0:
                    ctxt, ccol = f"Venceu ha {abs(dias)} dia{'s' if abs(dias)!=1 else ''}", WARNING
                elif dias == 0:
                    ctxt, ccol = "Vence hoje!", ORANGE
                elif dias <= 7:
                    ctxt, ccol = f"Vence em {dias} dia{'s' if dias!=1 else ''}", ORANGE
                else:
                    ctxt, ccol = f"Vence em {dias} dias", TEXT_GRAY
                lbl_ct = QLabel(f"  ·  {ctxt}")
                lbl_ct.setStyleSheet(f"font-size:11px; color:{ccol}; font-weight:600;")
                mid.addWidget(lbl_ct)
        mid.addStretch()

        if dias is not None and dias < 0:
            b_bg, b_fg, b_bd, b_tx = "#fee2e2", WARNING, "#fca5a5", "VENCIDO"
        else:
            b_bg, b_fg, b_bd, b_tx = "#fff7ed", ORANGE, "#fed7aa", "EM ABERTO"
        badge = QLabel(b_tx)
        badge.setStyleSheet(
            f"background:{b_bg}; color:{b_fg}; border:1px solid {b_bd};"
            f"border-radius:10px; padding:2px 10px; font-size:10px; font-weight:700;"
        )
        mid.addWidget(badge)
        root.addLayout(mid)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background:{BORDER}; border:none;")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        btns = QHBoxLayout()
        btns.setSpacing(8)

        if pag.get("codcliente") and pag.get("codcobranca"):
            btn_pix = QPushButton("Pagar com Pix")
            btn_pix.setFixedHeight(34)
            btn_pix.setStyleSheet(f"""
                QPushButton {{
                    background:{UNI_BLUE}; color:white; border:none;
                    border-radius:7px; font-size:12px; font-weight:600; padding:0 14px;
                }}
                QPushButton:hover {{ background:{UNI_BLUE2}; }}
            """)
            cc, cb = pag["codcliente"], pag["codcobranca"]
            btn_pix.clicked.connect(lambda _, c=cc, b=cb: self.pix_clicked.emit(c, b))
            btns.addWidget(btn_pix)

        if pag.get("boleto_key"):
            btn_bol = QPushButton("Ver Boleto")
            btn_bol.setFixedHeight(34)
            btn_bol.setStyleSheet(f"""
                QPushButton {{
                    background:white; color:{UNI_BLUE};
                    border:1.5px solid {UNI_BLUE}; border-radius:7px;
                    font-size:12px; font-weight:600; padding:0 14px;
                }}
                QPushButton:hover {{ background:{BG}; }}
            """)
            btn_bol.clicked.connect(lambda _, p=pag: self.boleto_clicked.emit(p))
            btns.addWidget(btn_bol)

        linha_dig = pag.get("linha_digitavel")
        if linha_dig:
            btn_cp = QPushButton("Copiar Codigo")
            btn_cp.setFixedHeight(34)
            btn_cp.setStyleSheet(f"""
                QPushButton {{
                    background:{BG}; color:{TEXT_GRAY};
                    border:1px solid {BORDER}; border-radius:7px;
                    font-size:12px; padding:0 14px;
                }}
                QPushButton:hover {{ background:{BORDER}; }}
            """)
            btn_cp.clicked.connect(lambda _, ld=linha_dig: self._copiar(ld))
            btns.addWidget(btn_cp)

        btn_wpp = QPushButton("WhatsApp")
        btn_wpp.setFixedHeight(34)
        btn_wpp.setStyleSheet("""
            QPushButton {
                background:#25D366; color:white; border:none;
                border-radius:7px; font-size:12px; font-weight:600; padding:0 14px;
            }
            QPushButton:hover { background:#128C7E; }
        """)
        wpp_msg = f"Ola! Cobrança Unifique: {desc_c} — {valor_txt} — Venc. {venc_str}"
        btn_wpp.clicked.connect(lambda _, m=wpp_msg: self._whatsapp(m))
        btns.addWidget(btn_wpp)

        btns.addStretch()
        root.addLayout(btns)

    def _copiar(self, codigo: str):
        QApplication.clipboard().setText(codigo)
        QMessageBox.information(self, "Copiado!", "Codigo de barras copiado para a area de transferencia.")

    def _whatsapp(self, msg: str):
        QDesktopServices.openUrl(QUrl("https://wa.me/?text=" + urllib.parse.quote(msg)))


# ── Main Window ───────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Unifique — Central do Assinante")
        self.setMinimumSize(960, 600)
        self.resize(1120, 740)
        self._cabecalho: list = []
        self._todos_dados: list = []
        self._todos_pags: list = []
        self._thread = None
        self._pix_thread = None
        self._prev_qtd: int | None = None
        self._setup_ui()
        self._setup_tray()
        self._setup_timer()
        QTimer.singleShot(300, self._buscar)

    # ─── UI setup ───────────────────────────────────────────

    def _setup_ui(self):
        raiz = QWidget()
        self.setCentralWidget(raiz)
        layout = QHBoxLayout(raiz)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Sidebar
        sidebar = QWidget()
        sidebar.setFixedWidth(230)
        sidebar.setStyleSheet(f"background:{UNI_BLUE};")
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)

        logo_area = QWidget()
        logo_area.setFixedHeight(72)
        ll = QHBoxLayout(logo_area)
        ll.setContentsMargins(18, 0, 18, 0)
        ll.setSpacing(12)
        icon_box = QLabel("U")
        icon_box.setFixedSize(38, 38)
        icon_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_box.setStyleSheet(f"background:{UNI_ACCENT}; color:white; font-size:18px; font-weight:700; border-radius:8px;")
        lbl_logo = QLabel("Unifique")
        lbl_logo.setStyleSheet("color:white; font-size:15px; font-weight:700;")
        ll.addWidget(icon_box); ll.addWidget(lbl_logo); ll.addStretch()
        sl.addWidget(logo_area)

        sl.addWidget(self._hdiv())
        sl.addSpacing(16)

        lbl_menu = QLabel("Menu")
        lbl_menu.setContentsMargins(20, 0, 0, 0)
        lbl_menu.setStyleSheet("color:rgba(255,255,255,0.35); font-size:10px; font-weight:600; letter-spacing:1px;")
        sl.addWidget(lbl_menu)
        sl.addSpacing(6)
        self._nav_item(sl, "Cobranças em Aberto", ativo=True)
        sl.addStretch()

        sl.addWidget(self._hdiv())
        sl.addSpacing(12)

        btn_pdf = QPushButton("Exportar PDF")
        btn_pdf.setFixedHeight(38)
        btn_pdf.setContentsMargins(16, 0, 16, 0)
        btn_pdf.setStyleSheet(f"""
            QPushButton {{
                background:rgba(255,255,255,0.1); color:rgba(255,255,255,0.85);
                border:1px solid rgba(255,255,255,0.2); border-radius:8px;
                font-size:12px; font-weight:600; margin:0 16px;
            }}
            QPushButton:hover {{ background:rgba(255,255,255,0.2); }}
        """)
        btn_pdf.clicked.connect(self._exportar_pdf)
        sl.addWidget(btn_pdf)
        sl.addSpacing(16)

        layout.addWidget(sidebar)

        # Main area
        main = QWidget()
        main.setStyleSheet(f"background:{BG};")
        ml = QVBoxLayout(main)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)

        topbar = QWidget()
        topbar.setFixedHeight(56)
        topbar.setStyleSheet(f"background:{CARD_BG}; border-bottom:1px solid {BORDER};")
        tl = QHBoxLayout(topbar)
        tl.setContentsMargins(20, 0, 20, 0)
        tl.setSpacing(12)

        btn_tog = QPushButton("☰")
        btn_tog.setFixedSize(36, 36)
        btn_tog.setStyleSheet(f"""
            QPushButton {{ background:transparent; color:{TEXT_GRAY}; border:none; font-size:18px; border-radius:6px; }}
            QPushButton:hover {{ background:{BG}; }}
        """)
        tl.addWidget(btn_tog)
        tl.addStretch()

        self.btn_atualizar = QPushButton("↻")
        self.btn_atualizar.setFixedSize(36, 36)
        self.btn_atualizar.setToolTip("Atualizar cobranças")
        self.btn_atualizar.setStyleSheet(f"""
            QPushButton {{
                background:{BG}; color:{UNI_BLUE}; border:1.5px solid {UNI_BLUE};
                border-radius:8px; font-size:18px; font-weight:700;
            }}
            QPushButton:hover {{ background:{UNI_BLUE}; color:white; }}
            QPushButton:disabled {{ color:#b0bec5; border-color:{BORDER}; }}
        """)
        self.btn_atualizar.clicked.connect(self._buscar)
        tl.addWidget(self.btn_atualizar)
        ml.addWidget(topbar)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(3)
        self.progress.setVisible(False)
        self.progress.setStyleSheet(
            f"QProgressBar {{ border:none; background:{BORDER}; }}"
            f"QProgressBar::chunk {{ background:{UNI_ACCENT}; }}"
        )
        ml.addWidget(self.progress)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"border:none; background:{BG};")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setStyleSheet(f"background:{BG};")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(28, 28, 28, 28)
        cl.setSpacing(20)

        tw = QWidget()
        tw.setStyleSheet("background:transparent;")
        twl = QVBoxLayout(tw)
        twl.setContentsMargins(0, 0, 0, 0)
        twl.setSpacing(2)
        twl.addWidget(self._lbl("Cobranças em Aberto", f"font-size:22px; font-weight:700; color:{TEXT_MAIN};"))
        twl.addWidget(self._lbl("Visao geral das suas cobranças — clique nos cards para pagar",
                                f"font-size:13px; color:{TEXT_GRAY};"))
        cl.addWidget(tw)

        stat_row = QHBoxLayout()
        stat_row.setSpacing(16)
        self.stat_qtd      = StatCard("Cobranças em Aberto", "—", UNI_ACCENT)
        self.stat_total    = StatCard("Total em Aberto",     "—", WARNING)
        self.stat_vencidas = StatCard("Vencidas",            "—", ORANGE)
        stat_row.addWidget(self.stat_qtd)
        stat_row.addWidget(self.stat_total)
        stat_row.addWidget(self.stat_vencidas)
        stat_row.addStretch()
        cl.addLayout(stat_row)

        self.filter_bar = FilterBar()
        self.filter_bar.changed.connect(self._aplicar_filtros)
        cl.addWidget(self.filter_bar)

        self.chart = ChartWidget()
        cl.addWidget(self.chart)

        self.cards_outer = QWidget()
        self.cards_outer.setStyleSheet("background:transparent;")
        self.cards_layout = QGridLayout(self.cards_outer)
        self.cards_layout.setSpacing(16)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(self.cards_outer)
        cl.addStretch()

        scroll.setWidget(content)
        ml.addWidget(scroll, 1)

        self.status = QStatusBar()
        self.status.setStyleSheet(
            f"background:{CARD_BG}; color:{TEXT_GRAY}; border-top:1px solid {BORDER}; font-size:12px;"
        )
        self.setStatusBar(self.status)
        layout.addWidget(main, 1)

    def _lbl(self, texto: str, style: str) -> QLabel:
        l = QLabel(texto)
        l.setStyleSheet(style)
        return l

    def _hdiv(self) -> QFrame:
        f = QFrame()
        f.setFixedHeight(1)
        f.setStyleSheet("background:rgba(255,255,255,0.1); border:none;")
        return f

    def _nav_item(self, layout, texto: str, ativo=False):
        btn = QWidget()
        btn.setFixedHeight(46)
        btn.setStyleSheet(f"""
            QWidget {{
                background:{'rgba(255,255,255,0.12)' if ativo else 'transparent'};
                border-left:3px solid {'white' if ativo else 'transparent'};
            }}
        """)
        row = QHBoxLayout(btn)
        row.setContentsMargins(20, 0, 20, 0)
        row.setSpacing(12)
        lbl = QLabel(texto)
        lbl.setStyleSheet(
            f"color:{'white' if ativo else 'rgba(255,255,255,0.65)'}; "
            f"font-size:13px; font-weight:{'600' if ativo else '400'}; border:none; background:transparent;"
        )
        row.addWidget(lbl)
        row.addStretch()
        layout.addWidget(btn)

    # ─── Tray & timer ────────────────────────────────────────

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = None
            return
        icon = _fazer_icon()
        self.setWindowIcon(icon)
        self._tray = QSystemTrayIcon(icon, self)
        menu = QMenu()
        act_show = QAction("Abrir", self)
        act_show.triggered.connect(self.show)
        act_quit = QAction("Sair", self)
        act_quit.triggered.connect(QApplication.quit)
        menu.addAction(act_show)
        menu.addSeparator()
        menu.addAction(act_quit)
        self._tray.setContextMenu(menu)
        self._tray.setToolTip("Unifique — Central do Assinante")
        self._tray.activated.connect(
            lambda r: self.show() if r == QSystemTrayIcon.ActivationReason.DoubleClick else None
        )
        self._tray.show()

    def _setup_timer(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(lambda: self._buscar(silencioso=True))
        self._timer.start(30 * 60 * 1000)

    # ─── Logic ───────────────────────────────────────────────

    def _buscar(self, silencioso=False):
        cpf   = os.getenv("UNIFIQUE_CPF", "").strip()
        senha = os.getenv("UNIFIQUE_SENHA", "").strip()
        if not cpf or not senha:
            QMessageBox.critical(self, "Credenciais ausentes",
                                 "Defina UNIFIQUE_CPF e UNIFIQUE_SENHA no arquivo .env")
            return
        self.btn_atualizar.setEnabled(False)
        self.progress.setVisible(True)
        if not silencioso:
            self.status.showMessage("Conectando ao portal Unifique...")
        self._limpar_cards()

        self._thread = BuscaThread(cpf, senha)
        self._thread.concluido.connect(
            lambda c, d, p: self._on_concluido(c, d, p, silencioso)
        )
        self._thread.erro.connect(self._on_erro)
        self._thread.start()

    def _limpar_cards(self):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_concluido(self, cabecalho, dados, pagamentos, silencioso=False):
        self.progress.setVisible(False)
        self.btn_atualizar.setEnabled(True)
        self._cabecalho   = cabecalho
        self._todos_dados = dados
        self._todos_pags  = pagamentos

        if silencioso and self._prev_qtd is not None and len(dados) > self._prev_qtd:
            diff = len(dados) - self._prev_qtd
            if self._tray:
                self._tray.showMessage(
                    "Unifique — Nova cobrança",
                    f"{diff} nova{'s' if diff!=1 else ''} cobrança{'s' if diff!=1 else ''} detectada{'s' if diff!=1 else ''}.",
                    QSystemTrayIcon.MessageIcon.Warning, 5000
                )
        self._prev_qtd = len(dados)
        self._aplicar_filtros()

    def _aplicar_filtros(self):
        self._limpar_cards()
        cabecalho  = self._cabecalho
        dados      = self._todos_dados
        pagamentos = self._todos_pags

        if not dados:
            self.stat_qtd.set_valor("0")
            self.stat_total.set_valor("R$ 0,00")
            self.stat_vencidas.set_valor("0")
            lbl = QLabel("Nenhuma cobrança em aberto ✓")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"font-size:15px; color:{SUCCESS}; padding:40px;")
            self.cards_layout.addWidget(lbl, 0, 0, 1, 2)
            self.status.showMessage("Sem cobranças em aberto.")
            self.chart.atualizar([], cabecalho)
            return

        val_idx  = next((i for i, h in enumerate(cabecalho) if "valor" in h.lower()), -1)
        venc_idx = next((i for i, h in enumerate(cabecalho) if "venc"  in h.lower()), -1)
        desc_idx = next((i for i, h in enumerate(cabecalho) if "desc"  in h.lower()), 0)

        total_all = sum(
            _parse_valor(l[val_idx]) for l in dados
            if val_idx != -1 and val_idx < len(l)
        )
        vencidas_all = sum(
            1 for l in dados
            if venc_idx != -1 and venc_idx < len(l)
            and (_dias_venc(l[venc_idx]) or 0) < 0
        )
        total_fmt = f"R$ {total_all:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        self.stat_qtd.set_valor(str(len(dados)))
        self.stat_total.set_valor(total_fmt)
        self.stat_vencidas.set_valor(str(vencidas_all))

        # Filter
        busca       = self.filter_bar.busca
        filtro_venc = self.filter_bar.filtro_venc
        hoje        = date.today()
        pares = list(zip(dados, pagamentos))

        if busca:
            pares = [(l, p) for l, p in pares
                     if busca in " ".join(str(c) for c in l).lower()]

        if filtro_venc != "Todos":
            def ok_venc(linha):
                v = linha[venc_idx] if venc_idx != -1 and venc_idx < len(linha) else ""
                d = _parse_venc(v)
                if d is None:
                    return True
                dias = (d - hoje).days
                if filtro_venc == "Hoje":        return dias == 0
                if filtro_venc == "Esta semana": return 0 <= dias <= 7
                if filtro_venc == "Este mes":    return 0 <= dias <= 30
                if filtro_venc == "Vencidos":    return dias < 0
                return True
            pares = [(l, p) for l, p in pares if ok_venc(l)]

        # Sort
        ord_ = self.filter_bar.ordenacao
        if ord_ == "Valor crescente":
            pares.sort(key=lambda x: _parse_valor(x[0][val_idx]) if val_idx != -1 and val_idx < len(x[0]) else 0)
        elif ord_ == "Valor decrescente":
            pares.sort(key=lambda x: _parse_valor(x[0][val_idx]) if val_idx != -1 and val_idx < len(x[0]) else 0, reverse=True)
        elif ord_ == "Venc. proximo":
            pares.sort(key=lambda x: _parse_venc(x[0][venc_idx]) or date.max
                       if venc_idx != -1 and venc_idx < len(x[0]) else date.max)
        elif ord_ == "Venc. distante":
            pares.sort(key=lambda x: _parse_venc(x[0][venc_idx]) or date.min
                       if venc_idx != -1 and venc_idx < len(x[0]) else date.min, reverse=True)

        if not pares:
            lbl = QLabel("Nenhuma cobrança encontrada para este filtro.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"font-size:14px; color:{TEXT_GRAY}; padding:40px;")
            self.cards_layout.addWidget(lbl, 0, 0, 1, 2)
        else:
            for i, (linha, pag) in enumerate(pares):
                card = CobrancaCard(linha, cabecalho, pag)
                card.pix_clicked.connect(self._abrir_pix)
                card.boleto_clicked.connect(self._abrir_boleto)
                self.cards_layout.addWidget(card, i // 2, i % 2)

        self.chart.atualizar([l for l, _ in pares], cabecalho)
        qtd = len(pares)
        self.status.showMessage(f"  {qtd} cobrança{'s' if qtd!=1 else ''} encontrada{'s' if qtd!=1 else ''}.")

    def _on_erro(self, msg):
        self.progress.setVisible(False)
        self.btn_atualizar.setEnabled(True)
        self.status.showMessage(f"Erro: {msg}")
        QMessageBox.critical(self, "Erro", msg)

    def _abrir_pix(self, codcliente: int, codcobranca: int):
        self.progress.setVisible(True)
        self.status.showMessage("Buscando codigo Pix...")
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
            QMessageBox.warning(self, "Pix indisponivel",
                                "Nao foi possivel obter o codigo Pix desta cobrança.")
            return
        PixDialog(code, resultado, self).exec()

    def _abrir_boleto(self, pag: dict):
        key = pag.get("boleto_key", "")
        if not key:
            QMessageBox.warning(self, "Boleto", "Chave do boleto nao encontrada.")
            return
        cpf   = os.getenv("UNIFIQUE_CPF", "").strip()
        senha = os.getenv("UNIFIQUE_SENHA", "").strip()
        BoletoDialog(fetcher.get_boleto_url(key), cpf, senha, self).exec()

    def _exportar_pdf(self):
        if not self._todos_dados:
            QMessageBox.information(self, "Exportar PDF",
                                    "Carregue as cobranças antes de exportar.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar PDF", "cobrancas_unifique.pdf", "PDF (*.pdf)"
        )
        if not path:
            return
        ok, info = _gerar_pdf(self._cabecalho, self._todos_dados, path)
        if ok:
            QMessageBox.information(self, "PDF exportado", f"Arquivo salvo em:\n{info}")
        else:
            QMessageBox.critical(self, "Erro ao exportar", info)

    def closeEvent(self, event):
        if self._tray and self._tray.isVisible():
            self.hide()
            self._tray.showMessage(
                "Unifique",
                "Rodando em segundo plano. Duplo clique no icone para abrir.",
                QSystemTrayIcon.MessageIcon.Information, 3000
            )
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Unifique Central")
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
