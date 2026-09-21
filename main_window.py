import customtkinter as ctk
import tkinter as tk
from PIL import Image
from datetime import datetime
from pathlib import Path
import threading, queue, sys, os, math, subprocess, time, random, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = HERE
for candidate in (HERE, os.path.dirname(HERE)):
    if os.path.exists(os.path.join(candidate, "kira_voice_agent.py")):
        PROJECT_ROOT = candidate
        sys.path.insert(0, candidate)
        break
try:
    import kira_voice_agent as backend
except Exception as exc:
    backend = None
    BACKEND_IMPORT_ERROR = exc

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")
BG = "#02060B"
SIDEBAR = "#040B13"
PANEL = "#07111B"
PANEL2 = "#091722"
BORDER = "#12344A"
TEXT = "#F4F8FF"
MUTED = "#6F879C"
ACCENT = "#FF2A2A"
ACCENT_WARM = "#FF3B30"
ACCENT_HOT = "#FF1744"
ACCENT_ALT = "#FF5252"
RED = "#FF1A1A"
AMBER = "#FFB84D"
FONT = "Segoe UI"


class KiraUI(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("KIRA — Local AI Computer Agent")
        self.geometry("1540x930")
        self.minsize(1180, 760)
        self.configure(fg_color=BG)
        self.phase = 0.0
        self.particle_phase = 0.0
        self.pulse = 0.0
        self.last_state = "READY"
        # ============================================================
        # MATRIX RED BACKGROUND
        # ============================================================

        self.matrix_canvas = None
        self.matrix_streams = []
        self.matrix_last_width = 0
        self.matrix_last_height = 0
        self.matrix_font = ("Consolas", 11)
        # KIRA application icon
        self.icon_path = Path(__file__).parent / "assets" / "kira_app.ico"
        self.logo_path = Path(__file__).parent / "assets" / "kira_app_icon.png"

        # Windows title bar / taskbar icon
        if self.icon_path.exists():
            try:
                self.iconbitmap(default=str(self.icon_path))
                self.iconbitmap(str(self.icon_path))
            except Exception:
                pass

        # Fallback for environments where .ico loading is unavailable
        if self.logo_path.exists():
            try:
                self._app_logo = tk.PhotoImage(file=str(self.logo_path))
                self.iconphoto(True, self._app_logo)
            except Exception:
                pass
        self.events = queue.Queue()
        self.busy = False
        self.listening = False
        self.speaking = False
        self.closing = False
        self._animation_job = None
        self._event_job = None
        self.phase = 0.0
        self.particle_phase = 0.0
        self.pulse = 0.0
        self.last_state = "READY"
        self._build_ui()
        self._animate()
        self._poll_events()
        self.protocol("WM_DELETE_WINDOW", self.close)
        if backend is None:
            self.set_state("ERROR", RED, "Backend could not be loaded")
            self.add_message("SYSTEM", f"Backend error: {BACKEND_IMPORT_ERROR}")
        else:
            self.add_message("KIRA", "Hello sir. I am ready for your orders.")
            self._update_statuses()

    def _build_ui(self):
        # ============================================================
        # KIRA — CINEMATIC CORE UI
        # ============================================================

        self.configure(fg_color="#010102")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ------------------------------------------------------------
        # ROOT
        # ------------------------------------------------------------

        root = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)

        root.grid(row=0, column=0, sticky="nsew")
        # ============================================================
        # ANIMATED RED MATRIX BACKGROUND
        # ============================================================

        self.matrix_canvas = tk.Canvas(
            root,
            bg="#010102",
            highlightthickness=0,
            bd=0,
        )

        self.matrix_canvas.place(
            relx=0,
            rely=0,
            relwidth=1,
            relheight=1,
        )

        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(1, weight=1)

        # ------------------------------------------------------------
        # TOP BAR
        # ------------------------------------------------------------

        top = ctk.CTkFrame(root, fg_color="transparent", height=65)

        top.grid(row=0, column=0, sticky="ew", padx=30, pady=(18, 0))

        top.grid_columnconfigure(1, weight=1)

        # KIRA mark

        ctk.CTkLabel(
            top,
            text="K I R A",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#EAFBFF",
        ).grid(row=0, column=0, sticky="w")

        # Core designation

        ctk.CTkLabel(
            top,
            text="AI CORE // LOCAL INSTANCE",
            font=ctk.CTkFont(size=8, weight="bold"),
            text_color="#385365",
        ).grid(row=0, column=1, sticky="w", padx=18)

        # Online indicator

        self.header_status = ctk.CTkLabel(
            top,
            text="● ONLINE",
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color="#20E58A",
        )

        self.header_status.grid(row=0, column=2, padx=15)

        # Model

        self.model_chip = ctk.CTkLabel(
            top,
            text=f"{getattr(backend, 'DEFAULT_MODEL', 'LOCAL')}",
            font=ctk.CTkFont(size=8),
            text_color="#5F7A8D",
        )

        self.model_chip.grid(row=0, column=3, padx=10)

        # Settings

        ctk.CTkButton(
            top,
            text="⚙",
            width=32,
            height=32,
            corner_radius=16,
            fg_color="transparent",
            hover_color="#0A1720",
            text_color="#4E6878",
            font=ctk.CTkFont(size=14),
            command=lambda: self.add_message(
                "SYSTEM", "KIRA settings are controlled through kira_config.json."
            ),
        ).grid(row=0, column=4)

        # ------------------------------------------------------------
        # MAIN CORE AREA
        # ------------------------------------------------------------

        core_area = ctk.CTkFrame(root, fg_color="transparent")

        core_area.grid(row=1, column=0, sticky="nsew", padx=30, pady=5)

        core_area.grid_columnconfigure(0, weight=1)
        core_area.grid_rowconfigure(0, weight=1)

        # ------------------------------------------------------------
        # CONVERSATION — FLOATING LEFT
        # ------------------------------------------------------------

        conversation = ctk.CTkFrame(
            core_area,
            width=330,
            fg_color="transparent",
            corner_radius=16,
            border_width=1,
            border_color="#4A0808",
        )

        conversation.place(relx=0.02, rely=0.15, relwidth=0.28, relheight=0.62)
        # Matrix glass background for conversation panel
        self.conversation_matrix = tk.Canvas(
            conversation,
            bg="#020101",
            highlightthickness=0,
            bd=0,
        )

        self.conversation_matrix.place(
            relx=0,
            rely=0,
            relwidth=1,
            relheight=1,
        )

        ctk.CTkLabel(
            conversation,
            text="CONVERSATION",
            font=ctk.CTkFont(size=8, weight="bold"),
            text_color="#3D6274",
        ).pack(anchor="w", padx=16, pady=(15, 5))

        self.chat = ctk.CTkTextbox(
            conversation,
            fg_color="transparent",
            border_width=0,
            text_color="#DCECF2",
            font=ctk.CTkFont(size=11),
            wrap="word",
            activate_scrollbars=True,
        )

        self.chat.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.chat.configure(state="disabled")

        # ------------------------------------------------------------
        # CENTRAL CORE
        # ------------------------------------------------------------

        center = ctk.CTkFrame(core_area, fg_color="transparent")

        center.place(relx=0.30, rely=0.02, relwidth=0.40, relheight=0.90)

        # Large animated canvas

        self.canvas = tk.Canvas(
            center,
            bg="#010102",
            highlightthickness=0,
            bd=0,
        )

        self.canvas.pack(fill="both", expand=True)

        # State

        self.state_label = ctk.CTkLabel(
            center,
            text="STANDBY",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#4C7385",
        )

        self.state_label.place(relx=0.5, rely=0.76, anchor="center")

        self.detail_label = ctk.CTkLabel(
            center,
            text="KIRA CORE ONLINE",
            font=ctk.CTkFont(size=8),
            text_color="#294553",
        )

        self.detail_label.place(relx=0.5, rely=0.80, anchor="center")

        # Technical labels

        ctk.CTkLabel(
            center,
            text="NEURAL ENGINE",
            font=ctk.CTkFont(size=7, weight="bold"),
            text_color="#264352",
        ).place(relx=0.5, rely=0.87, anchor="center")

        # ------------------------------------------------------------
        # RIGHT SYSTEM HUD
        # ------------------------------------------------------------

        system = ctk.CTkFrame(
            core_area,
            width=260,
            fg_color="transparent",
            corner_radius=16,
            border_width=1,
            border_color="#4A0808",
        )

        system.place(relx=0.71, rely=0.15, relwidth=0.27, relheight=0.62)
        # Matrix glass background for system panel
        self.system_matrix = tk.Canvas(
            system,
            bg="#020101",
            highlightthickness=0,
            bd=0,
        )

        self.system_matrix.place(
            relx=0,
            rely=0,
            relwidth=1,
            relheight=1,
        )

        ctk.CTkLabel(
            system,
            text="SYSTEM STATUS",
            font=ctk.CTkFont(size=8, weight="bold"),
            text_color="#3D6274",
        ).pack(anchor="w", padx=18, pady=(15, 15))

        def hud_metric(label):

            row = ctk.CTkFrame(system, fg_color="transparent", height=30)

            row.pack(fill="x", padx=18, pady=2)

            row.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(
                row, text=label, font=ctk.CTkFont(size=8), text_color="#456273"
            ).grid(row=0, column=0, sticky="w")

            value = ctk.CTkLabel(
                row,
                text="--",
                font=ctk.CTkFont(size=9, weight="bold"),
                text_color="#C9EAF2",
            )

            value.grid(row=0, column=1, sticky="e")

            return value

        self.cpu_label = hud_metric("CPU")
        self.ram_label = hud_metric("MEMORY")
        self.gpu_label = hud_metric("GPU")

        ctk.CTkFrame(system, height=1, fg_color="transparent").pack(
            fill="x", padx=18, pady=16
        )

        ctk.CTkLabel(
            system,
            text="CORE",
            font=ctk.CTkFont(size=8, weight="bold"),
            text_color="#3D6274",
        ).pack(anchor="w", padx=18, pady=(0, 8))

        self.model_label = ctk.CTkLabel(
            system,
            text=getattr(backend, "DEFAULT_MODEL", "LOCAL"),
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color="#BEEBF4",
        )

        self.model_label.pack(anchor="w", padx=18)

        ctk.CTkLabel(
            system,
            text="LOCAL AI MODEL",
            font=ctk.CTkFont(size=7),
            text_color="#345463",
        ).pack(anchor="w", padx=18, pady=(1, 10))

        ctk.CTkLabel(
            system,
            text="ACTIVITY",
            font=ctk.CTkFont(size=8, weight="bold"),
            text_color="#3D6274",
        ).pack(anchor="w", padx=18, pady=(8, 7))

        self.activity_label = ctk.CTkLabel(
            system,
            text="●  STANDBY",
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color="#20E58A",
        )

        self.activity_label.pack(anchor="w", padx=18)

        # Existing animation waveform

        self.wave = tk.Canvas(
            system, width=190, height=45, bg="#020101", highlightthickness=0, bd=0
        )

        self.wave.pack(padx=18, pady=(15, 8))

        # Legacy compatibility

        self.date_label = ctk.CTkLabel(system, text="")

        self.clock_label = ctk.CTkLabel(system, text="")

        # ------------------------------------------------------------
        # BOTTOM COMMAND INTERFACE
        # ------------------------------------------------------------

        command = ctk.CTkFrame(root, fg_color="transparent", height=105)

        command.grid(row=2, column=0, sticky="ew", padx=100, pady=(0, 18))

        command.grid_columnconfigure(0, weight=1)

        # Main input

        composer = ctk.CTkFrame(
            command,
            height=58,
            fg_color="transparent",
            corner_radius=18,
            border_width=1,
            border_color="#DA1923",
        )

        composer.grid(row=0, column=0, sticky="ew")

        composer.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            composer,
            placeholder_text="Ask KIRA...",
            height=48,
            border_width=0,
            fg_color="transparent",
            text_color="#E7F8FC",
            placeholder_text_color="#DA1923",
            font=ctk.CTkFont(size=13),
        )

        self.entry.grid(row=0, column=0, sticky="ew", padx=(18, 5), pady=5)

        self.entry.bind("<Return>", lambda _e: self.send_message())

        # Voice

        self.mic_btn = ctk.CTkButton(
            composer,
            text="🎙",
            width=42,
            height=42,
            corner_radius=21,
            fg_color="transparent",
            hover_color="#DA1923",
            text_color="#DA1923",
            font=ctk.CTkFont(size=14),
            command=self.toggle_listening,
        )

        self.mic_btn.grid(row=0, column=1, padx=2, pady=8)

        # Send

        self.send_btn = ctk.CTkButton(
            composer,
            text="➤",
            width=42,
            height=42,
            corner_radius=21,
            fg_color="transparent",
            hover_color="#FF5555",
            text_color="#021015",
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.send_message,
        )

        self.send_btn.grid(row=0, column=2, padx=(2, 8), pady=8)

        # Quick commands

        quick = ctk.CTkFrame(command, fg_color="transparent")

        quick.grid(row=1, column=0, sticky="w", pady=(7, 0))

        def quick_command(text):

            btn = ctk.CTkButton(
                quick,
                text=text,
                height=22,
                corner_radius=11,
                fg_color="#120304",
                hover_color="#350707",
                border_width=1,
                border_color="#5A0A0A",
                text_color="#466877",
                font=ctk.CTkFont(size=8),
                command=lambda t=text: self._use_suggestion(t),
            )

            btn.pack(side="left", padx=(0, 6))

        quick_command("OPEN CHROME")
        quick_command("ANALYZE SCREEN")
        quick_command("SYSTEM STATUS")

    def _build_sidebar(self):
        s = ctk.CTkFrame(
            self,
            fg_color="transparent",
            corner_radius=0,
            border_width=1,
            border_color="#0A2232",
        )
        s.grid(row=0, column=0, sticky="nsew")
        s.grid_rowconfigure(10, weight=1)
        brand = ctk.CTkFrame(s, fg_color="transparent")
        brand.pack(fill="x", padx=20, pady=(22, 28))
        # KIRA application logo
        logo_path = Path(__file__).parent / "assets" / "kira_app_icon.png"
        if logo_path.exists():
            try:
                self.logo_image = ctk.CTkImage(
                    light_image=Image.open(logo_path),
                    dark_image=Image.open(logo_path),
                    size=(54, 54),
                )
                logo = ctk.CTkLabel(
                    brand, image=self.logo_image, text="", fg_color="transparent"
                )
                logo.pack(side="left", padx=(0, 10))
            except Exception:
                logo = ctk.CTkLabel(
                    brand,
                    text="◉",
                    text_color=ACCENT,
                    font=ctk.CTkFont(size=30, weight="bold"),
                )
                logo.pack(side="left", padx=(0, 10))
        else:
            logo = ctk.CTkLabel(
                brand,
                text="◉",
                text_color=ACCENT,
                font=ctk.CTkFont(size=30, weight="bold"),
            )
            logo.pack(side="left", padx=(0, 10))
        labels = ctk.CTkFrame(brand, fg_color="transparent")
        labels.pack(side="left")
        ctk.CTkLabel(
            labels,
            text="KIRA",
            text_color=TEXT,
            font=ctk.CTkFont(size=27, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            labels,
            text="LOCAL AI COMPUTER AGENT",
            text_color=MUTED,
            font=ctk.CTkFont(size=8, weight="bold"),
        ).pack(anchor="w")
        self.nav_buttons = {}
        items = [
            ("▣", "Chat"),
            ("♩", "Voice"),
            ("⌘", "Commands"),
            ("◉", "Vision"),
            ("□", "Files"),
            ("⚒", "Tools"),
            ("◎", "Memory"),
            ("⚙", "Settings"),
        ]
        for icon, name in items:
            b = ctk.CTkButton(
                s,
                text=f"  {icon}    {name}",
                anchor="w",
                height=44,
                corner_radius=11,
                fg_color="transparent" if name == "Chat" else "transparent",
                hover_color="#0A2236",
                text_color=TEXT if name == "Chat" else "#A8BED2",
                font=ctk.CTkFont(
                    size=13, weight="bold" if name == "Chat" else "normal"
                ),
                command=lambda n=name: self._nav_click(n),
            )
            b.pack(fill="x", padx=12, pady=3)
            self.nav_buttons[name] = b
        info = ctk.CTkFrame(
            s,
            fg_color="#06111B",
            border_width=1,
            border_color="#0D2A3C",
            corner_radius=16,
        )
        info.pack(fill="x", padx=16, pady=(12, 16))
        ctk.CTkLabel(
            info,
            text="LOCAL • PRIVATE",
            text_color=ACCENT,
            font=ctk.CTkFont(size=9, weight="bold"),
        ).pack(anchor="w", padx=14, pady=(13, 5))
        ctk.CTkLabel(
            info,
            text="A smarter computer experience.\nBuilt around your local AI.",
            text_color=MUTED,
            justify="left",
            font=ctk.CTkFont(size=10),
        ).pack(anchor="w", padx=14, pady=(0, 14))
        ctk.CTkLabel(
            s,
            text="KIRA CORE  •  v4.0",
            text_color="#3E596C",
            font=ctk.CTkFont(size=8, weight="bold"),
        ).pack(side="bottom", pady=10)

    def _nav_click(self, n):
        if n == "Chat":
            self.entry.focus_set()
        elif n == "Voice":
            self.toggle_listening()
        else:
            self.set_state("READY", ACCENT, f"{n} module selected")

    def _build_header(self, p):
        h = ctk.CTkFrame(p, fg_color="transparent", height=72)
        h.grid(row=0, column=0, sticky="ew")
        h.grid_columnconfigure(0, weight=1)
        left = ctk.CTkFrame(h, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            left,
            text="KIRA CORE",
            text_color=TEXT,
            font=ctk.CTkFont(size=23, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            left,
            text="NEURAL INTERFACE  /  LOCAL AI COMPUTER AGENT",
            text_color=MUTED,
            font=ctk.CTkFont(size=8, weight="bold"),
        ).pack(anchor="w")
        m = ctk.CTkFrame(
            h, fg_color="#06101A", border_width=1, border_color=BORDER, corner_radius=16
        )
        m.grid(row=0, column=1, sticky="e")
        model = getattr(backend, "MODEL", "OFFLINE") if backend else "OFFLINE"
        self.model_chip = ctk.CTkLabel(
            m,
            text=f"◈  {str(model).upper()}",
            text_color=ACCENT,
            font=ctk.CTkFont(size=9, weight="bold"),
        )
        self.model_chip.pack(side="left", padx=14, pady=12)
        self.cpu_label = self._metric(m, "CPU", "--")
        self.ram_label = self._metric(m, "RAM", "--")
        online = ctk.CTkFrame(m, fg_color="#071B17", corner_radius=11)
        online.pack(side="left", padx=(7, 9), pady=7)
        self.status_dot = ctk.CTkLabel(
            online, text="●", text_color=ACCENT_ALT, font=ctk.CTkFont(size=11)
        )
        self.status_dot.pack(side="left", padx=(10, 4), pady=5)
        self.status_text = ctk.CTkLabel(
            online,
            text="ONLINE",
            text_color=TEXT,
            font=ctk.CTkFont(size=9, weight="bold"),
        )
        self.status_text.pack(side="left", padx=(0, 10))

    def _metric(self, p, l, v):
        f = ctk.CTkFrame(p, fg_color="transparent")
        f.pack(side="left", padx=7)
        ctk.CTkLabel(
            f, text=l, text_color=MUTED, font=ctk.CTkFont(size=7, weight="bold")
        ).pack()
        x = ctk.CTkLabel(
            f, text=v, text_color=TEXT, font=ctk.CTkFont(size=10, weight="bold")
        )
        x.pack()
        return x

    def _build_core(self, p):
        panel = ctk.CTkFrame(
            p, fg_color=PANEL, border_width=1, border_color=BORDER, corner_radius=22
        )
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(panel, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=22, pady=(15, 0))
        ctk.CTkLabel(
            top,
            text="KIRA CORE",
            text_color=ACCENT,
            font=ctk.CTkFont(size=10, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            top,
            text="NEURAL INTERFACE",
            text_color=MUTED,
            font=ctk.CTkFont(size=8, weight="bold"),
        ).pack(side="right")
        stage = ctk.CTkFrame(
            panel,
            fg_color="#020913",
            corner_radius=18,
            border_width=1,
            border_color="#3A0808",
        )
        stage.grid(row=1, column=0, sticky="nsew", padx=12, pady=12)
        stage.grid_rowconfigure(0, weight=1)
        stage.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(stage, bg="transparent", highlightthickness=0, bd=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda e: self._draw_orb())
        self.state_label = ctk.CTkLabel(
            panel,
            text="READY",
            text_color=ACCENT,
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        self.state_label.grid(row=2, column=0, pady=(0, 0))
        self.detail_label = ctk.CTkLabel(
            panel,
            text="Waiting for your command",
            text_color=MUTED,
            font=ctk.CTkFont(size=10),
        )
        self.detail_label.grid(row=3, column=0, pady=(0, 5))
        self.wave = tk.Canvas(panel, height=58, bg=PANEL, highlightthickness=0)
        self.wave.grid(row=4, column=0, sticky="ew", padx=45, pady=(0, 4))
        cards = ctk.CTkFrame(panel, fg_color="transparent")
        cards.grid(row=5, column=0, sticky="ew", padx=15, pady=(0, 14))
        cards.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)
        self.core_cards = []
        for i, (icon, name, color) in enumerate(
            [
                ("○", "READY", ACCENT),
                ("♩", "LISTENING", ACCENT_ALT),
                ("◈", "THINKING", ACCENT_HOT),
                ("⌁", "EXECUTING", ACCENT_WARM),
                ("◉", "SPEAKING", ACCENT),
            ]
        ):
            f = ctk.CTkFrame(
                cards,
                fg_color=PANEL2,
                border_width=1,
                border_color="#123046",
                corner_radius=12,
            )
            f.grid(row=0, column=i, sticky="ew", padx=3)
            ctk.CTkLabel(
                f, text=icon, text_color=color, font=ctk.CTkFont(size=17, weight="bold")
            ).pack(pady=(6, 0))
            ctk.CTkLabel(
                f, text=name, text_color=MUTED, font=ctk.CTkFont(size=7, weight="bold")
            ).pack(pady=(0, 6))
            self.core_cards.append((f, color))

    def _build_chat(self, p):
        panel = ctk.CTkFrame(
            p,
            fg_color="transparent",
            border_width=1,
            border_color=BORDER,
            corner_radius=22,
        )
        panel.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)
        top = ctk.CTkFrame(panel, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 10))
        ctk.CTkLabel(
            top,
            text="CONVERSATION",
            text_color=TEXT,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(side="left")
        self.model_label = ctk.CTkLabel(
            top,
            text="LOCAL",
            text_color=ACCENT_HOT,
            font=ctk.CTkFont(size=8, weight="bold"),
        )
        self.model_label.pack(side="right")
        self.chat = ctk.CTkTextbox(
            panel,
            fg_color="#06101A",
            border_width=1,
            border_color="#0D2738",
            corner_radius=15,
            text_color=TEXT,
            font=ctk.CTkFont(size=11),
            wrap="word",
        )
        self.chat.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 9))
        self.chat.configure(state="disabled")
        q = ctk.CTkFrame(panel, fg_color="transparent")
        q.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 7))
        for label, cmd in [
            ("Open VS Code", "open vscode"),
            ("Take Screenshot", "take screenshot"),
            ("System Info", "system info"),
            ("Open YouTube", "open youtube"),
        ]:
            ctk.CTkButton(
                q,
                text=label,
                height=29,
                corner_radius=9,
                fg_color="#260707",
                hover_color="#4A0A0A",
                border_width=1,
                border_color="#4A0A0A",
                text_color="#B9CCDC",
                font=ctk.CTkFont(size=8, weight="bold"),
                command=lambda c=cmd: self._quick(c),
            ).pack(side="left", padx=2)
        inp = ctk.CTkFrame(panel, fg_color="transparent")
        inp.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 12))
        inp.grid_columnconfigure(0, weight=1)
        self.entry = ctk.CTkEntry(
            inp,
            height=49,
            fg_color=PANEL2,
            border_color="#153A51",
            border_width=1,
            corner_radius=14,
            placeholder_text="Type a message to KIRA...",
            font=ctk.CTkFont(size=11),
        )
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 7))
        self.entry.bind("<Return>", lambda _: self.send_message())
        self.mic_btn = ctk.CTkButton(
            inp,
            text="♩",
            width=48,
            height=49,
            corner_radius=14,
            fg_color=PANEL2,
            hover_color="#10283C",
            border_width=1,
            border_color=BORDER,
            command=self.toggle_listening,
        )
        self.mic_btn.grid(row=0, column=1, padx=(0, 7))
        self.send_btn = ctk.CTkButton(
            inp,
            text="➤",
            width=57,
            height=49,
            corner_radius=14,
            fg_color=ACCENT_WARM,
            hover_color="#FF625A",
            font=ctk.CTkFont(size=18, weight="bold"),
            command=self.send_message,
        )
        self.send_btn.grid(row=0, column=2)

    def _quick(self, c):
        if not self.busy:
            self.entry.delete(0, "end")
            self.entry.insert(0, c)
            self.send_message()

    def _build_bottom(self, p):
        bar = ctk.CTkFrame(
            p,
            fg_color="#06101A",
            border_width=1,
            border_color=BORDER,
            corner_radius=17,
            height=65,
        )
        bar.grid(row=2, column=0, sticky="ew")
        bar.grid_columnconfigure(1, weight=1)
        left = ctk.CTkFrame(bar, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w", padx=15)
        ctk.CTkLabel(left, text="♫", text_color=ACCENT, font=ctk.CTkFont(size=20)).pack(
            side="left", padx=(0, 9)
        )
        ctk.CTkLabel(
            left,
            text="KIRA MEDIA",
            text_color=TEXT,
            font=ctk.CTkFont(size=9, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            left,
            text="Voice • media • system controls",
            text_color=MUTED,
            font=ctk.CTkFont(size=8),
        ).pack(anchor="w")
        ctr = ctk.CTkFrame(bar, fg_color="transparent")
        ctr.grid(row=0, column=1, sticky="w", padx=30)
        for t, c in [
            ("|◀", "media_previous"),
            ("▶", "media_play_pause"),
            ("▶|", "media_next"),
        ]:
            ctk.CTkButton(
                ctr,
                text=t,
                width=38,
                height=30,
                fg_color="transparent",
                hover_color="#102437",
                text_color="#B8C9D8",
                command=lambda x=c: self._quick(x),
            ).pack(side="left", padx=2)
        clk = ctk.CTkFrame(bar, fg_color="transparent")
        clk.grid(row=0, column=2, sticky="e", padx=18)
        self.clock_label = ctk.CTkLabel(
            clk, text="", text_color=TEXT, font=ctk.CTkFont(size=12, weight="bold")
        )
        self.clock_label.pack(anchor="e")
        self.date_label = ctk.CTkLabel(
            clk, text="", text_color=MUTED, font=ctk.CTkFont(size=8)
        )
        self.date_label.pack(anchor="e")

    def add_message(self, speaker, message):
        self.chat.configure(state="normal")
        ts = datetime.now().strftime("%H:%M")
        tag = {"KIRA": "kira", "MIND": "mind"}.get(speaker.upper(), "you")
        self.chat.insert("end", f"{speaker.upper()}   {ts}\n", tag)
        self.chat.insert("end", f"{message}\n\n", "body")
        self.chat.tag_config("kira", foreground=ACCENT)
        self.chat.tag_config("mind", foreground=MUTED)
        self.chat.tag_config("you", foreground="#B9C8FF")
        self.chat.tag_config("body", foreground=TEXT)
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def set_state(self, state, color, detail):
        self.last_state = state

        self.state_label.configure(text=state, text_color=color)
        self.detail_label.configure(text=detail)

        status_text = {
            "ERROR": "ERROR",
            "LISTENING": "LISTENING",
            "THINKING": "THINKING",
            "EXECUTING": "EXECUTING",
            "SPEAKING": "SPEAKING",
        }.get(state, "ONLINE")

        status_color = {
            "ERROR": RED,
            "LISTENING": ACCENT_ALT,
            "THINKING": ACCENT_HOT,
            "EXECUTING": ACCENT_WARM,
            "SPEAKING": ACCENT,
        }.get(state, ACCENT)

        if hasattr(self, "header_status"):
            self.header_status.configure(
                text=f"● {status_text}",
                text_color=status_color,
            )

        if hasattr(self, "status_text"):
            self.status_text.configure(text=status_text)

        if hasattr(self, "status_dot"):
            self.status_dot.configure(text_color=status_color)

        if hasattr(self, "core_cards"):
            for frame, card_color in self.core_cards:
                frame.configure(fg_color=PANEL2, border_color="#123046")

            state_index = {
                "READY": 0,
                "LISTENING": 1,
                "THINKING": 2,
                "EXECUTING": 3,
                "SPEAKING": 4,
            }.get(state)

            if state_index is not None:
                frame, card_color = self.core_cards[state_index]
                frame.configure(fg_color="#0B2435", border_color=card_color)

        self._draw_orb()

    def _set_busy(self, b):
        self.busy = b
        self.send_btn.configure(state="disabled" if b else "normal")
        self.entry.configure(state="disabled" if b else "normal")

    def _set_status(self, w, color, text):
        w.configure(text_color=color, text=text)

    def _ollama_ready(self, timeout=0.7):
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:11434/api/tags", timeout=timeout
            ) as r:
                return 200 <= r.status < 300
        except (OSError, urllib.error.URLError):
            return False

    def _ensure_ollama(self):
        if self._ollama_ready():
            return True, "Ollama connected"
        self.events.put(("ollama_starting", None))
        try:
            flags = (
                subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
                if os.name == "nt"
                else 0
            )
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=flags,
                close_fds=True,
            )
        except FileNotFoundError:
            return False, "Ollama is not installed or not in PATH"
        except Exception as e:
            return False, str(e)
        end = time.monotonic() + 12
        while time.monotonic() < end:
            if self._ollama_ready():
                return True, "Ollama started"
            time.sleep(0.35)
        return False, "Ollama did not become ready"

    def send_message(self):
        if self.busy or backend is None:
            return
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self.add_message("YOU", text)
        self.set_state("THINKING", ACCENT_HOT, "Understanding your request...")
        self._set_busy(True)
        threading.Thread(target=self._process, args=(text,), daemon=True).start()

    def _process(self, text):
        try:
            self.events.put(("reply", self._route(text)))
        except Exception as e:
            self.events.put(("error", f"{type(e).__name__}: {e}"))

    def _route(self, text):
        cleaned = backend.normalize_command(text)
        if not cleaned:
            return ""
        result = backend.parse_simple_command(cleaned)
        if result is None and backend.is_chat_question(cleaned):
            ok, d = self._ensure_ollama()
            return (
                backend.ask_chat(cleaned) if ok else f"I could not start Ollama. {d}."
            )
        planned_by = "parser"
        if result is None:
            ok, d = self._ensure_ollama()
            if not ok:
                return f"I could not start Ollama. {d}."

            # think before acting — recall first, LLM plan second; the
            # thought trace is shown in the chat panel (never spoken)
            thought = backend.think_about(cleaned)
            if thought.text:
                self.events.put(("thought", thought.text))
            result = thought.action
            planned_by = thought.source

        action = (result or {}).get("action", "none")
        if action == "conversation_on":
            backend._CONVERSATION_MODE = True
            return "Conversation mode is on."
        if action == "conversation_off":
            backend._CONVERSATION_MODE = False
            return "Conversation mode is off."
        if action == "chat_reset":
            backend.reset_chat()
            return "New conversation started."
        if action == "mode_info":
            return "Unified mode is active."
        if action == "none":
            ok, d = self._ensure_ollama()
            return (
                backend.ask_chat(cleaned) if ok else f"I could not start Ollama. {d}."
            )
        if backend.requires_confirmation(action) and not backend.confirm_action(
            action.replace("_", " "), backend.describe_action(result)
        ):
            return "Action cancelled."
        self.events.put(
            ("state", ("EXECUTING", ACCENT_WARM, f"Executing: {action.replace('_', ' ')}"))
        )

        success = backend.execute_action(result)

        if planned_by in {"llm", "memory"}:
            # reflect on what just happened
            backend.learn_from(cleaned, result, planned_by, bool(success))

        if isinstance(success, str):
            return success

        if not success:
            return backend.build_reply(backend.detect_language(cleaned), "none")

        target = ""

        if action in {"open_app", "open_url", "open_folder", "press"}:
            target = str(result.get("target", ""))
        elif action == "search":
            target = str(result.get("query", ""))

        return backend.build_reply(backend.detect_language(cleaned), action, target)

    def _speak(self, text):
        self.events.put(("speaking_start", None))
        try:
            backend.speak(text)
        except Exception as e:
            self.events.put(("error", f"Voice output failed: {e}"))
            return
        self.events.put(("speaking_done", None))

    def toggle_listening(self):
        if backend is None or self.busy or self.listening:
            return
        self.listening = True
        self._set_busy(True)
        self.mic_btn.configure(text="●", fg_color="#123B2B")
        self.set_state("LISTENING", ACCENT_ALT, "Speak to KIRA...")
        threading.Thread(target=self._listen, daemon=True).start()

    def _listen(self):
        try:
            self.events.put(
                (
                    "heard",
                    backend.listen_for_command(timeout=20, phrase_timeout=10) or "",
                )
            )
        except Exception as e:
            self.events.put(("error", f"{type(e).__name__}: {e}"))

    def _heard(self, text):
        self.listening = False
        self.mic_btn.configure(text="♩", fg_color=PANEL2)
        self._set_busy(False)
        if not text:
            self.set_state("READY", ACCENT, "I didn't hear a command")
            return
        self.add_message("YOU", text)
        self.set_state("THINKING", ACCENT_HOT, "Processing your voice command...")
        self._set_busy(True)
        threading.Thread(target=self._process, args=(text,), daemon=True).start()

    def _update_statuses(self):
        if backend is None:
            return
        model = str(
            getattr(backend, "MODEL", getattr(backend, "DEFAULT_MODEL", "OFFLINE"))
        ).upper()
        self.model_label.configure(text=f"{model} • LOCAL")
        self.model_chip.configure(text=f"◈  {model}")
        threading.Thread(
            target=lambda: self.events.put(("status", self._ollama_ready())),
            daemon=True,
        ).start()

    def _draw_orb(self):
        """Render the animated KIRA core and bottom audio waveform."""
        c = self.canvas
        w = max(400, c.winfo_width())
        h = max(400, c.winfo_height())

        c.delete("all")

        cx = w / 2
        cy = h / 2 - 8
        state = getattr(self, "last_state", "READY")

        # ---------------------------------------------------------
        # CENTRAL MATRIX BACKGROUND
        # ---------------------------------------------------------

        for i in range(32):
            x = (i * 47 + int(self.particle_phase * 35)) % w
            y = (i * 83 + int(self.phase * 22)) % h

            char = "1" if (i + int(self.phase * 2)) % 2 else "0"

            c.create_text(
                x,
                y,
                text=char,
                fill="#3A0608",
                font=("Consolas", 8),
                anchor="center",
            )

        profiles = {
            "READY": {
                "speed": 0.025,
                "pulse": 5,
                "edge": "#1599C2",
                "wave": 4,
                "rotation": 0.08,
            },
            "LISTENING": {
                "speed": 0.075,
                "pulse": 14,
                "edge": ACCENT_ALT,
                "wave": 18,
                "rotation": 0.25,
            },
            "THINKING": {
                "speed": 0.14,
                "pulse": 11,
                "edge": ACCENT_HOT,
                "wave": 14,
                "rotation": 0.55,
            },
            "EXECUTING": {
                "speed": 0.20,
                "pulse": 15,
                "edge": ACCENT_WARM,
                "wave": 20,
                "rotation": 0.85,
            },
            "SPEAKING": {
                "speed": 0.10,
                "pulse": 18,
                "edge": ACCENT,
                "wave": 28,
                "rotation": 0.35,
            },
            "ERROR": {
                "speed": 0.06,
                "pulse": 12,
                "edge": RED,
                "wave": 10,
                "rotation": 0.15,
            },
        }

        profile = profiles.get(state, profiles["READY"])
        pulse = (math.sin(self.phase * 2.0) + 1.0) / 2.0

        # Background particles
        for i in range(75):
            angle = i * 2.399 + self.particle_phase * (0.12 + (i % 4) * 0.01)
            radius = 105 + (i * 37) % 280
            drift = math.sin(self.phase * profile["rotation"] + i) * (
                2 if state != "READY" else 0.5
            )

            x = cx + math.cos(angle) * (radius + drift)
            y = cy + math.sin(angle) * (radius + drift) * 0.72
            size = 1 if i % 4 else 2

            particle_color = (
                profile["edge"] if i % 11 == 0 and state != "READY" else "#5A0808"
            )

            c.create_oval(
                x - size, y - size, x + size, y + size, fill=particle_color, outline=""
            )

        # Outer orbit rings
        rings = [
            (235, "#210506", 1),
            (215, "#3A0808", 1),
            (192, "#5C0D0D", 1),
            (170, profile["edge"], 2),
        ]

        for index, (radius, color, width) in enumerate(rings):
            expansion = profile["pulse"] * pulse
            if index < 2:
                expansion *= 0.35

            r = radius + expansion
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=color, width=width)

        # Rotating orbit markers
        for i in range(40):
            angle = i * math.tau / 40 + self.phase * profile["rotation"]
            radius = 196

            x1 = cx + math.cos(angle) * radius
            y1 = cy + math.sin(angle) * radius

            marker_length = 7 if i % 4 else 14
            x2 = cx + math.cos(angle) * (radius + marker_length)
            y2 = cy + math.sin(angle) * (radius + marker_length)

            marker_color = profile["edge"] if i % 5 == 0 else "#0D4058"

            c.create_line(
                x1, y1, x2, y2, fill=marker_color, width=2 if i % 5 == 0 else 1
            )

        # Core glow
        layers = [
            (158, "#100304"),
            (148, "#190506"),
            (138, "#260707"),
            (128, "#350909"),
            (118, "#220506"),
        ]

        for radius, color in layers:
            factor = profile["pulse"]
            if radius < 140:
                factor *= 0.8

            r = radius + pulse * factor
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color, outline="")

        edge_radius = 112 + pulse * profile["pulse"] * 0.35
        c.create_oval(
            cx - edge_radius,
            cy - edge_radius,
            cx + edge_radius,
            cy + edge_radius,
            outline=profile["edge"],
            width=4 if state != "READY" else 3,
        )

        # Neural waves
        wave_count = 7 if state in {"THINKING", "EXECUTING"} else 5

        for k in range(wave_count):
            points = []

            for x in range(-94, 95, 4):
                base_amp = 4 + k * 1.8
                dynamic_amp = (
                    profile["wave"] * pulse
                    + abs(math.sin(self.phase * 1.7 + k * 0.8)) * profile["wave"] * 0.4
                )

                y = (
                    math.sin(x * 0.055 + self.phase * (1.0 + profile["rotation"]) + k)
                    * (base_amp + dynamic_amp)
                    * math.sin((x + 95) * math.pi / 190)
                )

                if state == "SPEAKING":
                    y *= 1.0 + 0.35 * math.sin(self.phase * 3 + x * 0.03)

                points.extend([cx + x, cy + y + (k - (wave_count - 1) / 2) * 11])

            c.create_line(
                *points,
                fill=(profile["edge"] if k == wave_count // 2 else "#B51212"),
                width=3 if k == wave_count // 2 else 1,
                smooth=True,
            )

        # Central KIRA text
        c.create_text(cx, cy - 8, text="KIRA", fill=TEXT, font=(FONT, 30, "bold"))

        c.create_text(
            cx, cy + 25, text="CORE", fill=profile["edge"], font=(FONT, 9, "bold")
        )

        # Bottom audio waveform
        if hasattr(self, "wave"):
            wc = self.wave
            ww = max(250, wc.winfo_width())
            wh = 58
            wc.delete("all")
            mid = wh / 2

            waveform_strength = {
                "READY": 3,
                "LISTENING": 20,
                "THINKING": 13,
                "EXECUTING": 19,
                "SPEAKING": 27,
                "ERROR": 9,
            }.get(state, 4)

            for i in range(41):
                x = 15 + i * (ww - 30) / 40
                movement = abs(math.sin(i * 0.52 + self.phase * 3))

                amp = 3 + waveform_strength * movement * (0.45 + pulse * 0.8)

                if state == "READY":
                    amp = 2 + movement * 2

                wc.create_line(
                    x,
                    mid - amp,
                    x,
                    mid + amp,
                    fill="#FF2A2A" if i % 4 == 0 else "#7A0C0C",
                    width=2 if i % 4 == 0 else 1,
                )

            wc.create_line(
                10,
                mid,
                ww - 10,
                mid,
                fill="#0B2C3C",
                width=1,
            )

        # Advance animation only after all drawing is complete.
        self.phase += profile["speed"]
        self.particle_phase += 0.012

    def _draw_panel_matrix(self, canvas, phase_offset=0):
        """Draw subtle red Matrix rain inside a HUD panel."""

        width = canvas.winfo_width()
        height = canvas.winfo_height()

        if width < 50 or height < 50:
            return

        canvas.delete("panel_matrix")

        spacing = 17
        columns = max(1, width // spacing)

        for column in range(columns):

            x = column * spacing + 6

            speed = 1.5 + (column % 5) * 0.35

            stream_y = (self.phase * speed * 8 + column * 43 + phase_offset) % (
                height + 250
            ) - 250

            length = 10 + (column * 5) % 14

            for i in range(length):

                y = stream_y - i * 15

                if y < -20 or y > height + 20:
                    continue

                if i == 0:
                    color = "#FF4545"
                elif i < 3:
                    color = "#D71919"
                elif i < 6:
                    color = "#8A1010"
                elif i < 10:
                    color = "#4A0808"
                else:
                    color = "#250404"

                char = "1" if (column + i + int(self.phase * 2)) % 2 else "0"

                canvas.create_text(
                    x,
                    y,
                    text=char,
                    fill=color,
                    font=("Consolas", 9),
                    anchor="center",
                    tags="panel_matrix",
                )

    def _draw_matrix(self):
        """Animated red Matrix-style falling 0/1 background."""

        if self.matrix_canvas is None:
            return

        canvas = self.matrix_canvas

        width = canvas.winfo_width()
        height = canvas.winfo_height()

        if width < 100 or height < 100:
            return

        # ---------------------------------------------------------
        # INITIALIZE MATRIX STREAMS
        # ---------------------------------------------------------

        if (
            width != self.matrix_last_width
            or height != self.matrix_last_height
            or not self.matrix_streams
        ):
            self.matrix_last_width = width
            self.matrix_last_height = height

            column_spacing = 15
            column_count = max(1, width // column_spacing)

            self.matrix_streams = []

            for column in range(column_count):

                self.matrix_streams.append(
                    {
                        "x": column * column_spacing + random.randint(-2, 2),
                        # Start streams throughout the screen
                        "y": random.randint(-300, height),
                        # Different speeds
                        "speed": random.uniform(2.0, 6.5),
                        # Longer streams
                        "length": random.randint(10, 30),
                        # Random character phase
                        "phase": random.randint(0, 20),
                        # Different brightness
                        "brightness": random.random(),
                    }
                )

        canvas.delete("matrix")

        characters = ("0", "1")

        # ---------------------------------------------------------
        # MATRIX DIGITAL RAIN
        # ---------------------------------------------------------

        for stream in self.matrix_streams:

            x = stream["x"]
            y = stream["y"]
            speed = stream["speed"]
            length = stream["length"]
            phase = stream["phase"]

            for i in range(length):

                char_y = y - (i * 16)

                if char_y < -25 or char_y > height + 25:
                    continue

                # Character changes over time
                char = characters[int(phase + i + self.phase * 3) % 2]

                # Bright glowing head
                if i == 0:
                    color = "#FF5555"

                # Bright red
                elif i == 1:
                    color = "#FF2A2A"

                # Medium red
                elif i < 4:
                    color = "#E51E25"

                # Dark red
                elif i < 8:
                    color = "#9E1118"

                # Fading tail
                elif i < 14:
                    color = "#4A0808"

                else:
                    color = "#3A0608"

                canvas.create_text(
                    x,
                    char_y,
                    text=char,
                    fill=color,
                    font=("Consolas", 11),
                    anchor="center",
                    tags="matrix",
                )

            # Move stream
            stream["y"] += speed

            # Restart from the top
            if y - (length * 16) > height:

                stream["y"] = random.randint(-400, -20)
                stream["speed"] = random.uniform(2.0, 6.5)
                stream["length"] = random.randint(10, 30)
                stream["phase"] = random.randint(0, 20)

        # ---------------------------------------------------------
        # SUBTLE RED DIGITAL GRID
        # ---------------------------------------------------------

        for x in range(0, width, 90):

            canvas.create_line(
                x,
                0,
                x,
                height,
                fill="#100202",
                width=1,
                tags="matrix",
            )

        canvas.tag_lower("matrix")

    def _animate(self):
        if self.closing:
            return

        self._draw_matrix()

        if hasattr(self, "conversation_matrix"):
            self._draw_panel_matrix(
                self.conversation_matrix,
                0,
            )

        if hasattr(self, "system_matrix"):
            self._draw_panel_matrix(
                self.system_matrix,
                120,
            )

        self._draw_orb()

        now = datetime.now()

        # The minimal UI does not require a visible clock/date.
        # Keep these updates optional so the animation can never crash
        # if a compact layout omits one of the legacy telemetry widgets.
        if hasattr(self, "clock_label"):
            self.clock_label.configure(text=now.strftime("%H:%M:%S"))
        if hasattr(self, "date_label"):
            self.date_label.configure(text=now.strftime("%a, %d %b %Y"))

        try:
            import psutil

            if hasattr(self, "cpu_label"):
                self.cpu_label.configure(
                    text=f"{psutil.cpu_percent(interval=None):.0f}%"
                )
            if hasattr(self, "ram_label"):
                self.ram_label.configure(text=f"{psutil.virtual_memory().percent:.0f}%")
        except Exception:
            pass

        self._animation_job = self.after(45, self._animate)

    def _poll_events(self):
        try:
            while True:
                k, p = self.events.get_nowait()
                if k == "reply":
                    if p:
                        self.add_message("KIRA", p)
                        threading.Thread(
                            target=self._speak, args=(p,), daemon=True
                        ).start()
                    else:
                        self.set_state("READY", ACCENT, "Waiting for your command")
                        self._set_busy(False)
                elif k == "thought":
                    # the agent's internal plan — displayed, never spoken
                    if p:
                        self.add_message("MIND", p)
                elif k == "state":
                    state, color, detail = p
                    self.set_state(state, color, detail)
                elif k == "speaking_start":
                    self.speaking = True
                    self.set_state("SPEAKING", ACCENT, "KIRA is speaking...")
                elif k == "speaking_done":
                    self.speaking = False
                    self.set_state("READY", ACCENT, "Waiting for your command")
                    self._set_busy(False)
                elif k == "heard":
                    self._heard(p)
                elif k == "ollama_starting":
                    self.set_state("THINKING", AMBER, "Starting local AI engine...")
                elif k == "status":
                    online = bool(p)

                    if hasattr(self, "header_status"):
                        self.header_status.configure(
                            text="● ONLINE" if online else "● LOCAL",
                            text_color=ACCENT_ALT if online else MUTED,
                        )

                    if hasattr(self, "status_dot"):
                        self.status_dot.configure(text_color=ACCENT_ALT if online else MUTED)

                    if hasattr(self, "status_text"):
                        self.status_text.configure(text="ONLINE" if online else "LOCAL")
                elif k == "error":
                    self.speaking = False
                    self.add_message("SYSTEM", p)
                    self.set_state("ERROR", RED, "Something went wrong")
                    self._set_busy(False)
                    self.listening = False
        except queue.Empty:
            pass
        if not self.closing:
            self._event_job = self.after(70, self._poll_events)

    def _use_suggestion(self, text):
        """Put a quick suggestion into the command field."""
        try:
            self.entry.delete(0, "end")
            self.entry.insert(0, text)
            self.entry.focus_set()
        except Exception:
            pass

    def close(self):
        self.closing = True
        try:
            self.after_cancel(getattr(self, "_animation_job", None))
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    app = KiraUI()
    app.mainloop()
