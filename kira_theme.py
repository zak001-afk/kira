import tkinter as tk
import customtkinter as ctk
import random
import math

# ============================================================
# KIRA // NEURAL COMMAND INTERFACE
# ============================================================

BG = "#020202"

RED = "#FF2020"
RED_BRIGHT = "#FF4545"
RED_DARK = "#650808"
RED_DEEP = "#250303"

WHITE = "#F4F4F4"
TEXT = "#D8D8D8"
MUTED = "#666666"

FONT = "Segoe UI"
MONO = "Consolas"


class KiraTheme(ctk.CTk):

    def __init__(self):
        super().__init__()

        # ----------------------------------------------------
        # WINDOW
        # ----------------------------------------------------

        self.title("KIRA — Local AI Computer Agent")

        self.geometry("1540x930")
        self.minsize(1180, 760)

        self.configure(fg_color=BG)

        # ----------------------------------------------------
        # ANIMATION
        # ----------------------------------------------------

        self.animation_running = True
        self.phase = 0.0

        # Matrix streams
        self.matrix_streams = []

        # ----------------------------------------------------
        # BUILD
        # ----------------------------------------------------

        self._build_background()
        self._build_header()
        self._build_core()
        self._build_panels()
        self._build_command_bar()

        # Start animation (50ms = 20fps for resource efficiency)
        self._frame_count = 0
        self.after(50, self._animate)

    # ========================================================
    # BACKGROUND
    # ========================================================

    def _build_background(self):

        self.background = tk.Canvas(
            self,
            bg=BG,
            highlightthickness=0,
            bd=0,
        )

        self.background.place(
            relx=0,
            rely=0,
            relwidth=1,
            relheight=1,
        )

        self.bind(
            "<Configure>",
            self._initialize_matrix,
        )

    # ========================================================
    # HEADER
    # ========================================================

    def _build_header(self):

        self.header = ctk.CTkFrame(
            self,
            width=1000,
            height=55,
            fg_color="transparent",
            corner_radius=0,
        )

        self.header.place(
            relx=0.025,
            rely=0.025,
            relwidth=0.95,
        )

        # KIRA logo

        ctk.CTkLabel(
            self.header,
            text="K I R A",
            font=ctk.CTkFont(
                family=FONT,
                size=20,
                weight="bold",
            ),
            text_color=WHITE,
        ).place(
            relx=0,
            rely=0.15,
        )

        # System designation

        ctk.CTkLabel(
            self.header,
            text="NEURAL COMPUTER AGENT // LOCAL INSTANCE",
            font=ctk.CTkFont(
                family=MONO,
                size=8,
            ),
            text_color=MUTED,
        ).place(
            relx=0.095,
            rely=0.28,
        )

        # Online status

        self.online_label = ctk.CTkLabel(
            self.header,
            text="● ONLINE",
            font=ctk.CTkFont(
                family=MONO,
                size=9,
                weight="bold",
            ),
            text_color=RED,
        )

        self.online_label.place(
            relx=0.90,
            rely=0.25,
        )

    # ========================================================
    # CORE
    # ========================================================

    def _build_core(self):

        self.core_canvas = tk.Canvas(
            self,
            bg=BG,
            highlightthickness=0,
            bd=0,
        )

        self.core_canvas.place(
            relx=0.27,
            rely=0.14,
            relwidth=0.46,
            relheight=0.65,
        )

    # ========================================================
    # PANELS
    # ========================================================
    def _draw_panel_frame(self, canvas, title):

        # Outer HUD frame

        width = 390
        height = 440

        canvas.create_rectangle(
            1,
            1,
            width - 2,
            height - 2,
            outline=RED_DARK,
            width=1,
            tags="panel",
        )

        # Top accent

        canvas.create_line(
            18,
            32,
            105,
            32,
            fill=RED,
            width=1,
            tags="panel",
        )

        # Title

        canvas.create_text(
            20,
            17,
            anchor="nw",
            text=title,
            fill=RED_BRIGHT,
            font=(MONO, 8, "bold"),
            tags="panel",
        )

        # Bottom accent

        canvas.create_line(
            18,
            height - 22,
            90,
            height - 22,
            fill=RED_DARK,
            width=1,
            tags="panel",
        )
        # Subtle HUD grid

        for x in range(40, width - 20, 50):

            canvas.create_line(
                x,
                45,
                x,
                height - 35,
                fill="#100303",
                width=1,
                tags="panel",
            )

        for y in range(70, height - 35, 45):

            canvas.create_line(
                15,
                y,
                width - 15,
                y,
                fill="#100303",
                width=1,
                tags="panel",
            )

    def _build_panels(self):

        # ====================================================
        # LEFT CONVERSATION PANEL
        # ====================================================

        self.left_panel = tk.Canvas(
            self,
            bg=BG,
            highlightthickness=0,
            bd=0,
        )

        self.left_panel.place(
            relx=0.035,
            rely=0.22,
            relwidth=0.255,
            relheight=0.48,
        )

        self._draw_panel_frame(
            self.left_panel,
            "CONVERSATION",
        )

        # Conversation text

        self.left_message = self.left_panel.create_text(
            25,
            70,
            anchor="nw",
            text=("KIRA  //  15:05\n\n" "Hello sir.\n" "I am ready for your orders."),
            fill=TEXT,
            font=(MONO, 10),
            tags="panel",
        )

        # ====================================================
        # RIGHT SYSTEM PANEL
        # ====================================================

        self.right_panel = tk.Canvas(
            self,
            bg=BG,
            highlightthickness=0,
            bd=0,
        )

        self.right_panel.place(
            relx=0.71,
            rely=0.22,
            relwidth=0.255,
            relheight=0.48,
        )

        self._draw_panel_frame(
            self.right_panel,
            "SYSTEM TELEMETRY",
        )

        # Telemetry

        self.right_panel.create_text(
            25,
            70,
            anchor="nw",
            text="CPU",
            fill=MUTED,
            font=(MONO, 8),
            tags="panel",
        )

        self.cpu_value = self.right_panel.create_text(
            300,
            70,
            anchor="ne",
            text="-- %",
            fill=WHITE,
            font=(MONO, 9, "bold"),
            tags="panel",
        )

        self.right_panel.create_text(
            25,
            105,
            anchor="nw",
            text="MEMORY",
            fill=MUTED,
            font=(MONO, 8),
            tags="panel",
        )

        self.memory_value = self.right_panel.create_text(
            300,
            105,
            anchor="ne",
            text="-- %",
            fill=WHITE,
            font=(MONO, 9, "bold"),
            tags="panel",
        )

        self.right_panel.create_text(
            25,
            140,
            anchor="nw",
            text="GPU",
            fill=MUTED,
            font=(MONO, 8),
            tags="panel",
        )

        self.gpu_value = self.right_panel.create_text(
            300,
            140,
            anchor="ne",
            text="--",
            fill=WHITE,
            font=(MONO, 9, "bold"),
            tags="panel",
        )

        # Core information

        self.right_panel.create_text(
            25,
            205,
            anchor="nw",
            text="CORE",
            fill=MUTED,
            font=(MONO, 8, "bold"),
            tags="panel",
        )

        self.right_panel.create_text(
            25,
            230,
            anchor="nw",
            text="LOCAL NEURAL ENGINE",
            fill=RED,
            font=(MONO, 9, "bold"),
            tags="panel",
        )

        # Activity

        self.right_panel.create_text(
            25,
            285,
            anchor="nw",
            text="ACTIVITY",
            fill=MUTED,
            font=(MONO, 8, "bold"),
            tags="panel",
        )

        self.activity_indicator = self.right_panel.create_oval(
            25,
            315,
            31,
            321,
            fill=RED,
            outline="",
            tags="panel",
        )

        self.activity_text = self.right_panel.create_text(
            42,
            318,
            anchor="w",
            text="STANDBY",
            fill=RED,
            font=(MONO, 9, "bold"),
            tags="panel",
        )

    # ========================================================
    # COMMAND BAR
    # ========================================================

    def _build_command_bar(self):

        self.command_canvas = tk.Canvas(
            self,
            bg=BG,
            highlightthickness=0,
            bd=0,
        )

        self.command_canvas.place(
            relx=0.065,
            rely=0.83,
            relwidth=0.87,
            height=70,
        )

        # Input

        self.command_entry = ctk.CTkEntry(
            self.command_canvas,
            placeholder_text="ASK KIRA...",
            fg_color="#070202",
            border_color=RED_DARK,
            border_width=1,
            text_color=WHITE,
            placeholder_text_color=MUTED,
            font=ctk.CTkFont(
                family=MONO,
                size=11,
            ),
            height=52,
            corner_radius=26,
        )

        self.command_entry.place(
            relx=0,
            rely=0,
            relwidth=1,
        )

    # ========================================================
    # MATRIX INITIALIZATION
    # ========================================================

    def _initialize_matrix(self, event=None):

        width = self.background.winfo_width()
        height = self.background.winfo_height()

        if width < 100 or height < 100:
            return

        columns = max(1, width // 22)

        self.matrix_streams = []

        for column in range(columns):

            self.matrix_streams.append(
                {
                    "x": column * 22,
                    "y": random.randint(
                        -height,
                        height,
                    ),
                    "speed": random.uniform(
                        1.5,
                        5.5,
                    ),
                    "length": random.randint(
                        8,
                        22,
                    ),
                }
            )

    # ========================================================
    # MATRIX
    # ========================================================

    def _draw_matrix(self):

        canvas = self.background

        width = canvas.winfo_width()
        height = canvas.winfo_height()

        if width < 100 or height < 100:
            return

        if not self.matrix_streams:
            self._initialize_matrix()

        canvas.delete("matrix")

        for stream in self.matrix_streams:

            x = stream["x"]
            y = stream["y"]
            length = stream["length"]

            for i in range(length):

                char_y = y - i * 17

                if char_y < -20:
                    continue

                if char_y > height + 20:
                    continue

                # Head

                if i == 0:

                    color = RED_BRIGHT

                # Bright trail

                elif i < 3:

                    color = RED

                # Medium trail

                elif i < 7:

                    color = RED_DARK

                # Fade

                else:

                    color = RED_DEEP

                char = "1" if random.random() > 0.5 else "0"

                canvas.create_text(
                    x,
                    char_y,
                    text=char,
                    fill=color,
                    font=(
                        MONO,
                        10,
                    ),
                    anchor="center",
                    tags="matrix",
                )

            stream["y"] += stream["speed"]

            # Restart

            if y - length * 17 > height:

                stream["y"] = random.randint(
                    -400,
                    -20,
                )

                stream["speed"] = random.uniform(
                    1.5,
                    5.5,
                )

                stream["length"] = random.randint(
                    8,
                    22,
                )

    # ========================================================
    # CORE DRAWING
    # ========================================================

    def _draw_core(self):

        canvas = self.core_canvas
        canvas.delete("core")

        width = canvas.winfo_width()
        height = canvas.winfo_height()

        if width < 200 or height < 200:
            return

        cx = width / 2
        cy = height / 2

        # ====================================================
        # ANIMATION VALUES
        # ====================================================

        t = self.phase

        pulse = (math.sin(t * 3.0) + 1.0) / 2.0

        rotation = t * 0.8

        # ====================================================
        # 3D FLOOR / REACTOR BASE
        # ====================================================

        base_y = cy + 185

        # Shadow

        canvas.create_oval(
            cx - 155,
            base_y - 18,
            cx + 155,
            base_y + 18,
            fill="#080101",
            outline="",
            tags="core",
        )

        # Lower platform

        canvas.create_oval(
            cx - 140,
            base_y - 20,
            cx + 140,
            base_y + 20,
            fill="#160303",
            outline=RED_DARK,
            width=2,
            tags="core",
        )

        canvas.create_oval(
            cx - 120,
            base_y - 13,
            cx + 120,
            base_y + 13,
            outline=RED,
            width=2,
            tags="core",
        )

        canvas.create_oval(
            cx - 95,
            base_y - 8,
            cx + 95,
            base_y + 8,
            outline="#7A0A0A",
            width=1,
            tags="core",
        )

        # ====================================================
        # 3D VERTICAL ENERGY BEAM
        # ====================================================

        beam_width = 20 + pulse * 12

        canvas.create_polygon(
            cx - beam_width,
            base_y - 5,
            cx + beam_width,
            base_y - 5,
            cx + beam_width * 0.55,
            cy - 205,
            cx - beam_width * 0.55,
            cy - 205,
            fill="#160202",
            outline="",
            tags="core",
        )

        canvas.create_line(
            cx,
            cy - 220,
            cx,
            base_y,
            fill=RED_DARK,
            width=1,
            tags="core",
        )

        # ====================================================
        # OUTER 3D ORBIT RINGS
        # ====================================================

        for i, radius in enumerate([215, 195, 175]):

            tilt = 0.28 + i * 0.06

            bbox = (
                cx - radius,
                cy - radius * tilt,
                cx + radius,
                cy + radius * tilt,
            )

            canvas.create_oval(
                *bbox,
                outline=(RED_DARK if i != 0 else "#7A0A0A"),
                width=1,
                tags="core",
            )

        # ====================================================
        # ROTATING ORBIT RINGS
        # ====================================================

        orbit_specs = [
            (150, 0.34, rotation),
            (135, 0.22, -rotation * 1.4),
            (120, 0.48, rotation * 0.7),
        ]

        for radius, tilt, angle in orbit_specs:

            # Main ellipse

            canvas.create_oval(
                cx - radius,
                cy - radius * tilt,
                cx + radius,
                cy + radius * tilt,
                outline=RED,
                width=2,
                tags="core",
            )

            # Rotating bright section

            segment = math.radians((angle * 180 / math.pi) % 360)

            for s in range(8):

                a = segment + s * 0.035

                x = cx + math.cos(a) * radius
                y = cy + math.sin(a) * radius * tilt

                canvas.create_oval(
                    x - 2,
                    y - 2,
                    x + 2,
                    y + 2,
                    fill=RED_BRIGHT,
                    outline="",
                    tags="core",
                )

        # ====================================================
        # KIRA VISAGE HOLOGRAMME -- REMPLACE LA SPHERE 3D
        # Le noyau/reacteur est remplacé par le visage de KIRA
        # à la place exacte du noyau (centre cx,cy)
        # ====================================================

        # Halos holographiques derrière le visage (remplace core glow)
        halo_r = 122 + pulse * 10
        canvas.create_oval(
            cx - halo_r, cy - halo_r, cx + halo_r, cy + halo_r,
            fill="#1a0505", outline="", tags="core",
        )
        canvas.create_oval(
            cx - halo_r*0.88, cy - halo_r*0.88, cx + halo_r*0.88, cy + halo_r*0.88,
            fill="#2a0808", outline=RED_DARK, width=1, tags="core",
        )
        # anneau lumineux autour du visage
        canvas.create_oval(
            cx - 118, cy - 142, cx + 118, cy + 142,
            outline=RED, width=2, tags="core",
        )
        canvas.create_oval(
            cx - 128, cy - 152, cx + 128, cy + 152,
            outline="#3a0a0a", width=1, tags="core",
        )

        # --- Visage base (oval) ---
        face_w = 92
        face_h = 118 + pulse * 5  # respire légèrement verticalement
        face_top = cy - 72
        face_bottom = face_top + face_h*2*0.72  # approx
        # on dessine l'ovale visage avec teinte peau légèrement rosée / holographique
        # ombre portée
        canvas.create_oval(
            cx - face_w -2, face_top -2, cx + face_w +2, face_top + face_h*1.45 +2,
            fill="#0d0202", outline="", tags="core",
        )
        # base visage
        canvas.create_oval(
            cx - face_w, face_top, cx + face_w, face_top + face_h*1.45,
            fill="#1c0f0f", outline=RED_DARK, width=1, tags="core",
        )
        # highlight peau (dégradé simulé par ovales plus clairs inset)
        canvas.create_oval(
            cx - face_w*0.78, face_top + 8, cx + face_w*0.78, face_top + face_h*1.30,
            fill="#2a1818", outline="", tags="core",
        )
        canvas.create_oval(
            cx - face_w*0.55, face_top + 18, cx + face_w*0.55, face_top + face_h*1.10,
            fill="#3a2424", outline="", tags="core",
        )

        # --- Cheveux / haut tête ---
        canvas.create_oval(
            cx - face_w*0.92, face_top - 12, cx + face_w*0.92, face_top + 42,
            fill="#080201", outline="#1a0a0a", width=1, tags="core",
        )
        # mèches holographiques cyan/rouge sur côtés
        for dx, col in [(-face_w*0.88, "#00d8ff"), (face_w*0.88, "#00d8ff")]:
            canvas.create_line(
                cx+dx, face_top+8, cx+dx*0.92, face_top+52,
                fill=col, width=1, tags="core",
            )

        # --- Cou / collier tech (comme sur l'image) ---
        neck_w = 42 + pulse*2
        neck_top = face_top + face_h*1.32
        canvas.create_rectangle(
            cx - neck_w, neck_top, cx + neck_w, neck_top + 28,
            fill="#070202", outline=RED_DARK, width=1, tags="core",
        )
        # lueur centrale verticale cyan
        canvas.create_line(
            cx, neck_top+2, cx, neck_top+22,
            fill="#00e5ff", width=2, tags="core",
        )
        # détails collier
        canvas.create_line(
            cx - neck_w + 6, neck_top+14, cx - 8, neck_top+14,
            fill="#333333", width=1, tags="core",
        )
        canvas.create_line(
            cx + 8, neck_top+14, cx + neck_w -6, neck_top+14,
            fill="#333333", width=1, tags="core",
        )

        # --- Circuit holographique joues (lignes qui pulsent avec voix) ---
        circuit_alpha = 0.6 + pulse*0.4
        cheek_y = face_top + face_h*0.58
        # joue gauche
        canvas.create_line(
            cx - 52, cheek_y - 6, cx - 28, cheek_y + 4, cx - 22, cheek_y + 18,
            fill=RED_BRIGHT if pulse>0.5 else "#00d8ff", width=1, smooth=True, tags="core",
        )
        # joue droite
        canvas.create_line(
            cx + 52, cheek_y - 6, cx + 28, cheek_y + 4, cx + 22, cheek_y + 18,
            fill=RED_BRIGHT if pulse>0.5 else "#00d8ff", width=1, smooth=True, tags="core",
        )
        # petits points lumineux aux tempes
        canvas.create_oval(cx - 44, face_top + 38, cx - 40, face_top + 42, fill="#00e5ff", outline="", tags="core")
        canvas.create_oval(cx + 40, face_top + 38, cx + 44, face_top + 42, fill="#00e5ff", outline="", tags="core")

        # --- Yeux (avec iris bleu cyan qui pulse) ---
        eye_y = face_top + 52
        eye_w = 24
        eye_h = 13 + pulse*1.2  # clignement subtil quand t varie? on module avec phase
        # petite fonction clignement auto tous les ~4 secondes
        blink = 1.0
        if (int(t*0.7) % 80 == 0):
            blink = 0.22
        eye_h_eff = eye_h * blink
        iris_pulse = 1.0 + pulse*0.12
        for dx in (-1, 1):
            ex = cx + dx*32
            # fond blanc oeil
            canvas.create_oval(
                ex - eye_w, eye_y - eye_h_eff, ex + eye_w, eye_y + eye_h_eff,
                fill="#0a0a0a", outline="#3a3a3a", width=1, tags="core",
            )
            # iris bleu cyan brillant
            iris_r = 9 * iris_pulse
            canvas.create_oval(
                ex - iris_r, eye_y - iris_r*0.92, ex + iris_r, eye_y + iris_r*0.92,
                fill="#0ab8ff", outline="#00e5ff", width=1, tags="core",
            )
            # pupille
            canvas.create_oval(
                ex - 4.5, eye_y - 5, ex + 4.5, eye_y + 5,
                fill="#00141f", outline="", tags="core",
            )
            # reflet lumineux
            canvas.create_oval(
                ex - 2, eye_y - 4, ex + 2, eye_y - 1,
                fill="#ffffff", outline="", tags="core",
            )
            # lueur externe yeux (glow)
            glow = 0.7 + pulse*0.3
            canvas.create_oval(
                ex - eye_w -2, eye_y - eye_h_eff -2, ex + eye_w +2, eye_y + eye_h_eff +2,
                outline="#00d8ff", width=1, tags="core",
            )

        # --- Sourcils ---
        brow_y = eye_y - 16
        canvas.create_line(cx - 54, brow_y, cx - 18, brow_y - 2, fill="#2a2a2a", width=2, tags="core")
        canvas.create_line(cx + 18, brow_y - 2, cx + 54, brow_y, fill="#2a2a2a", width=2, tags="core")

        # --- Nez ---
        nose_top = face_top + 58
        nose_bottom = face_top + 84
        canvas.create_line(
            cx, nose_top, cx - 3, nose_bottom - 6, cx + 3, nose_bottom,
            fill="#1a0a0a", width=1, smooth=True, tags="core",
        )
        # narines subtiles
        canvas.create_oval(cx - 7, nose_bottom -2, cx - 3, nose_bottom+1, fill="#1e0f0f", outline="", tags="core")
        canvas.create_oval(cx + 3, nose_bottom -2, cx + 7, nose_bottom+1, fill="#1e0f0f", outline="", tags="core")

        # --- Bouche / lèvres (s'anime avec pulse = simulation voix) ---
        mouth_y = face_top + 98
        mouth_open = 3 + pulse * 7  # 3=fermé, 10=ouverte quand KIRA parle
        mouth_w = 22 + pulse * 4
        # lèvre supérieure
        canvas.create_line(
            cx - mouth_w, mouth_y, cx, mouth_y - 1, cx + mouth_w, mouth_y,
            fill="#4a2020", width=2, smooth=True, tags="core",
        )
        # ouverture bouche (intérieur sombre)
        canvas.create_oval(
            cx - mouth_w*0.62, mouth_y - 1, cx + mouth_w*0.62, mouth_y + mouth_open,
            fill="#120202" if mouth_open<6 else "#1a0a0a", outline="#6a2a2a", width=1, tags="core",
        )
        # lèvres inférieures highlight
        canvas.create_line(
            cx - mouth_w*0.62, mouth_y + mouth_open, cx, mouth_y + mouth_open + 1, cx + mouth_w*0.62, mouth_y + mouth_open,
            fill="#8a3a3a", width=1, smooth=True, tags="core",
        )
        # reflet lèvres
        canvas.create_line(
            cx - mouth_w*0.38, mouth_y + 1, cx - 2, mouth_y + 2,
            fill="#c06060", width=1, tags="core",
        )

        # --- Menton / contour visage léger lueur rouge ---
        canvas.create_arc(
            cx - face_w*0.72, face_top + face_h*0.9, cx + face_w*0.72, face_top + face_h*1.38,
            start=200, extent=140, style="arc", outline=RED_DARK, width=1, tags="core",
        )

        # --- Scanline holographique sur visage ---
        for sy in range(0, int(face_h*1.3), 14):
            y = face_top + 12 + sy + int(pulse*4) % 14
            if face_top + 10 < y < face_top + face_h*1.35:
                canvas.create_line(
                    cx - face_w*0.82, y, cx + face_w*0.82, y,
                    fill="#ff202014", width=1, tags="core",
                )

        # --- Nom KIRA sous le visage (remplace ancien KIRA central) ---
        canvas.create_text(
            cx, neck_top + 42,
            text="KIRA",
            fill=WHITE,
            font=(FONT, 18, "bold"),
            tags="core",
        )
        canvas.create_text(
            cx, neck_top + 60,
            text="VISAGE HOLOGRAMME • VOIX SYNC",
            fill=RED_BRIGHT,
            font=(MONO, 7, "bold"),
            tags="core",
        )

        # --- Indicateur READY juste sous ---
        dot_pulse = 0.6 + pulse*0.4
        dot_col = RED_BRIGHT if dot_pulse>0.7 else "#ff6a6a"
        canvas.create_oval(
            cx - 28, neck_top + 74, cx - 22, neck_top + 80,
            fill=dot_col, outline="", tags="core",
        )
        canvas.create_text(
            cx - 14, neck_top + 77,
            text="VISAGE ACTIF // PRET",
            anchor="w",
            fill=RED_BRIGHT,
            font=(MONO, 7, "bold"),
            tags="core",
        )

        # ====================================================
        # TECHNICAL LABELS
        # ====================================================

        canvas.create_text(
            cx,
            cy - 235,
            text="KIRA // NEURAL PROCESSOR",
            fill="#650808",
            font=(MONO, 7),
            tags="core",
        )

        canvas.create_text(
            cx,
            base_y + 30,
            text="KIRA CORE // ONLINE",
            fill=RED_DARK,
            font=(MONO, 7),
            tags="core",
        )

    # ========================================================
    # ANIMATION
    # ========================================================

    def _animate(self):

        if not self.animation_running:
            return

        self._frame_count += 1

        # Slower phase increment for 50ms interval (was 0.035 at 30ms)
        self.phase += 0.025

        self._draw_matrix()
        self._draw_core()

        self.after(
            50,
            self._animate,
        )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")

    app = KiraTheme()

    app.mainloop()
