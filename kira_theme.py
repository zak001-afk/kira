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

        # Start animation
        self.after(30, self._animate)

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
        # 3D SPHERE
        # ====================================================

        sphere = 112

        # Outer dark sphere

        canvas.create_oval(
            cx - sphere,
            cy - sphere,
            cx + sphere,
            cy + sphere,
            fill="#080101",
            outline="#4A0505",
            width=2,
            tags="core",
        )

        # Layered spherical shading

        shading = [
            (105, "#0D0101"),
            (96, "#120202"),
            (87, "#180303"),
            (78, "#200404"),
            (69, "#280505"),
        ]

        for radius, fill in shading:

            # Offset toward upper-left to simulate light

            offset_x = -8
            offset_y = -10

            canvas.create_oval(
                cx - radius + offset_x,
                cy - radius + offset_y,
                cx + radius + offset_x,
                cy + radius + offset_y,
                fill=fill,
                outline="",
                tags="core",
            )

        # ====================================================
        # SPHERE OUTLINE
        # ====================================================

        canvas.create_oval(
            cx - sphere,
            cy - sphere,
            cx + sphere,
            cy + sphere,
            outline=RED,
            width=2,
            tags="core",
        )

        # ====================================================
        # LATITUDE LINES
        # ====================================================

        latitude_specs = [
            (0.72, 0.18),
            (0.48, 0.30),
            (0.24, 0.42),
            (0.00, 0.50),
            (-0.24, 0.42),
            (-0.48, 0.30),
            (-0.72, 0.18),
        ]

        for vertical, width_factor in latitude_specs:

            y = cy + vertical * sphere

            half_width = sphere * width_factor

            canvas.create_arc(
                cx - half_width,
                y - sphere * 0.18,
                cx + half_width,
                y + sphere * 0.18,
                start=0,
                extent=360,
                style="arc",
                outline="#650808",
                width=1,
                tags="core",
            )

        # ====================================================
        # LONGITUDE LINES
        # ====================================================

        for i in range(8):

            angle = i * math.pi / 8 + rotation * 0.25

            squash = abs(math.cos(angle))

            half_width = max(8, sphere * squash)

            canvas.create_oval(
                cx - half_width,
                cy - sphere,
                cx + half_width,
                cy + sphere,
                outline="#4A0505",
                width=1,
                tags="core",
            )

        # ====================================================
        # CENTRAL ENERGY CORE
        # ====================================================

        core_radius = 43 + pulse * 6

        canvas.create_oval(
            cx - core_radius - 8,
            cy - core_radius - 8,
            cx + core_radius + 8,
            cy + core_radius + 8,
            outline="#650808",
            width=2,
            tags="core",
        )

        canvas.create_oval(
            cx - core_radius,
            cy - core_radius,
            cx + core_radius,
            cy + core_radius,
            fill="#190202",
            outline=RED_BRIGHT,
            width=2,
            tags="core",
        )

        # Inner energy layers

        for i in range(3):

            r = core_radius - 8 - i * 8

            canvas.create_oval(
                cx - r,
                cy - r,
                cx + r,
                cy + r,
                outline="#7A0A0A",
                width=1,
                tags="core",
            )

        # ====================================================
        # NEURAL WAVEFORM
        # ====================================================

        points = []

        for x in range(-65, 66, 3):

            wave = math.sin(x * 0.13 + t * 5)

            wave2 = math.sin(x * 0.045 - t * 2)

            amplitude = 7 + pulse * 8

            y = cy + wave * amplitude + wave2 * 3

            points.extend(
                [
                    cx + x,
                    y,
                ]
            )

        canvas.create_line(
            *points,
            fill=RED_BRIGHT,
            width=2,
            smooth=True,
            tags="core",
        )

        # ====================================================
        # ORBITING ENERGY PARTICLES
        # ====================================================

        for i in range(16):

            angle = t * 1.2 + i * math.pi * 2 / 16

            radius = 145

            x = cx + math.cos(angle) * radius
            y = cy + math.sin(angle) * radius * 0.35

            size = 2 if i % 3 else 3

            canvas.create_oval(
                x - size,
                y - size,
                x + size,
                y + size,
                fill=RED_BRIGHT,
                outline="",
                tags="core",
            )

        # ====================================================
        # KIRA TEXT
        # ====================================================

        canvas.create_text(
            cx,
            cy - 8,
            text="KIRA",
            fill=WHITE,
            font=(
                FONT,
                30,
                "bold",
            ),
            tags="core",
        )

        canvas.create_text(
            cx,
            cy + 27,
            text="NEURAL CORE",
            fill=RED_BRIGHT,
            font=(
                MONO,
                8,
                "bold",
            ),
            tags="core",
        )

        # ====================================================
        # STATUS
        # ====================================================

        canvas.create_oval(
            cx - 32,
            cy + 52,
            cx - 26,
            cy + 58,
            fill=RED_BRIGHT,
            outline="",
            tags="core",
        )

        canvas.create_text(
            cx - 18,
            cy + 55,
            text="READY",
            anchor="w",
            fill=RED_BRIGHT,
            font=(
                MONO,
                8,
                "bold",
            ),
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

        self.phase += 0.035

        self._draw_matrix()
        self._draw_core()

        self.after(
            30,
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
