import os
import time
import math
import random
import statistics
import threading
import hashlib
from collections import deque, defaultdict
from datetime import datetime

from dash import Dash, dcc, html, Input, Output, no_update
import plotly.graph_objects as go


# ============================================================
# UTILITIES
# ============================================================

def clamp(v, lo=0.0, hi=1.0):
    try:
        if v is None: return lo
        v = float(v)
        if math.isnan(v) or math.isinf(v): return lo
        return max(lo, min(hi, v))
    except Exception:
        return lo

def clamp100(v):
    return clamp(v, 0, 100)

def now_hms():
    return datetime.now().strftime("%H:%M:%S")

def weighted_choice(rng, items, weights):
    try:
        if not items: return None
        total = sum(max(0.001, w) for w in weights)
        r = rng.random() * total
        acc = 0
        for item, w in zip(items, weights):
            acc += max(0.001, w)
            if r <= acc: return item
        return items[-1]
    except Exception:
        return items[0] if items else None


# ============================================================
# LEVEL 1: CELLULAR SIMULATION
# ============================================================

class Cell:
    """
    شبیه‌سازی یک سلول با متابولیسم، انرژی، و چرخه حیات.
    """
    def __init__(self, cell_type, rng):
        self.id = rng.randint(0, 10**9)
        self.cell_type = cell_type
        self.energy = rng.uniform(60, 100)
        self.health = rng.uniform(80, 100)
        self.age = 0
        self.max_age = rng.randint(500, 2000)
        self.alive = True
        self.metabolic_rate = rng.uniform(0.8, 1.2)
        self.specialization = rng.uniform(0.5, 1.0)

    def tick(self, oxygen, nutrients, waste):
        if not self.alive: return

        self.age += 1

        # Metabolism
        energy_gain = oxygen * 0.3 + nutrients * 0.5
        energy_cost = 0.5 * self.metabolic_rate + waste * 0.2
        self.energy = clamp100(self.energy + energy_gain - energy_cost)

        # Health affected by energy and waste
        if self.energy < 20:
            self.health -= 1.5
        if waste > 60:
            self.health -= 0.8

        # Aging
        if self.age > self.max_age:
            self.health -= 2.0

        # Death
        if self.health <= 0 or self.energy <= 0:
            self.alive = False

    def divide(self, rng):
        if self.alive and self.energy > 70 and self.health > 60 and rng.random() < 0.02:
            self.energy -= 30
            return Cell(self.cell_type, rng)
        return None


class CellPopulation:
    """
    جمعیت سلول‌های یک بافت خاص.
    """
    def __init__(self, cell_type, count, rng):
        self.cell_type = cell_type
        self.cells = [Cell(cell_type, rng) for _ in range(count)]
        self.rng = rng

    def tick(self, oxygen, nutrients, waste):
        alive_cells = []
        new_cells = []

        for cell in self.cells:
            cell.tick(oxygen, nutrients, waste)
            if cell.alive:
                alive_cells.append(cell)
                new_cell = cell.divide(self.rng)
                if new_cell:
                    new_cells.append(new_cell)

        self.cells = alive_cells + new_cells

        # Cap population
        if len(self.cells) > 200:
            self.cells = self.cells[:200]

    @property
    def alive_count(self):
        return len(self.cells)

    @property
    def avg_health(self):
        if not self.cells: return 0
        return sum(c.health for c in self.cells) / len(self.cells)

    @property
    def avg_energy(self):
        if not self.cells: return 0
        return sum(c.energy for c in self.cells) / len(self.cells)


# ============================================================
# LEVEL 2: TISSUE SIMULATION
# ============================================================

class Tissue:
    """
    بافت متشکل از جمعیت سلول‌ها.
    """
    def __init__(self, name, cell_type, cell_count, rng):
        self.name = name
        self.population = CellPopulation(cell_type, cell_count, rng)
        self.blood_supply = 0.8
        self.innervation = 0.7

    def tick(self, oxygen, nutrients, waste):
        effective_oxygen = oxygen * self.blood_supply
        effective_nutrients = nutrients * self.blood_supply
        self.population.tick(effective_oxygen, effective_nutrients, waste)

    @property
    def health(self):
        return self.population.avg_health

    @property
    def function(self):
        return self.population.avg_energy * self.population.avg_health / 100


# ============================================================
# LEVEL 3: ORGAN SIMULATION
# ============================================================

class Organ:
    """
    ارگان متشکل از چند بافت با عملکرد خاص.
    """
    def __init__(self, name, tissues, function_type, rng):
        self.name = name
        self.tissues = tissues
        self.function_type = function_type
        self.blood_flow = 0.8
        self.neural_input = 0.5
        self.hormonal_input = 0.5
        self.stress_level = 0.0
        self.rng = rng

    def tick(self, oxygen, nutrients, waste, neural_signal, hormonal_signal):
        self.neural_input = clamp(neural_signal)
        self.hormonal_input = clamp(hormonal_signal)

        # Stress from low resources
        resource_stress = max(0, 50 - oxygen * 0.5 - nutrients * 0.3)
        self.stress_level = clamp100(0.8 * self.stress_level + 0.2 * resource_stress)

        for tissue in self.tissues:
            tissue.blood_supply = self.blood_flow
            tissue.tick(oxygen, nutrients, waste)

    @property
    def health(self):
        if not self.tissues: return 50
        return sum(t.health for t in self.tissues) / len(self.tissues)

    @property
    def function_capacity(self):
        if not self.tissues: return 50
        base = sum(t.function for t in self.tissues) / len(self.tissues)
        return base * (1 - self.stress_level / 200)

    def output_signal(self):
        return self.function_capacity / 100


# ============================================================
# LEVEL 4: ORGAN SYSTEM SIMULATION
# ============================================================

class OrganSystem:
    """
    سیستم ارگانی متشکل از چند ارگان.
    """
    def __init__(self, name, organs, system_type):
        self.name = name
        self.organs = organs
        self.system_type = system_type
        self.efficiency = 0.8

    def tick(self, oxygen, nutrients, waste, neural, hormonal):
        for organ in self.organs:
            organ.tick(oxygen, nutrients, waste, neural, hormonal)

    @property
    def health(self):
        if not self.organs: return 50
        return sum(o.health for o in self.organs) / len(self.organs)

    @property
    def function(self):
        if not self.organs: return 50
        return sum(o.function_capacity for o in self.organs) / len(self.organs)


# ============================================================
# LEVEL 5: FULL BODY INTEGRATION
# ============================================================

class HumanBody:
    """
    شبیه‌سازی یکپارچه بدن انسان از سلول تا ارگان.
    """
    def __init__(self, rng):
        self.rng = rng

        # Build tissues and organs
        self._build_body()

        # Body-wide signals
        self.oxygen = 85.0
        self.nutrients = 80.0
        self.waste = 15.0
        self.temperature = 37.0
        self.ph = 7.4
        self.hydration = 80.0
        self.hormones = {
            "adrenaline": 20.0,
            "cortisol": 30.0,
            "serotonin": 60.0,
            "dopamine": 50.0,
            "melatonin": 20.0,
            "insulin": 40.0,
        }

        # Neural signals from brain
        self.neural_commands = {
            "heart_rate": 70,
            "breathing_rate": 14,
            "digestion": 0.5,
            "muscle_tension": 0.3,
            "alertness": 0.5,
        }

        # Body state
        self.energy = 80.0
        self.stress = 20.0
        self.pain = 5.0
        self.fatigue = 15.0
        self.immune_activity = 50.0

    def _build_body(self):
        rng = self.rng

        # Nervous system
        brain_tissue = Tissue("بافت مغز", "neuron", 100, rng)
        spinal_tissue = Tissue("بافت نخاعی", "neuron", 30, rng)
        nerve_tissue = Tissue("اعصاب محیطی", "neuron", 40, rng)
        self.nervous_system = OrganSystem(
            "سیستم عصبی",
            [
                Organ("مغز", [brain_tissue], "processing", rng),
                Organ("نخاع", [spinal_tissue], "relay", rng),
                Organ("اعصاب", [nerve_tissue], "transmission", rng),
            ],
            "nervous"
        )

        # Cardiovascular system
        heart_tissue = Tissue("ماهیچه قلب", "cardiac_muscle", 60, rng)
        vessel_tissue = Tissue("رگ‌ها", "endothelial", 50, rng)
        blood_tissue = Tissue("خون", "blood_cell", 80, rng)
        self.cardiovascular_system = OrganSystem(
            "سیستم قلبی‌عروقی",
            [
                Organ("قلب", [heart_tissue], "pump", rng),
                Organ("رگ‌ها", [vessel_tissue], "transport", rng),
                Organ("خون", [blood_tissue], "carriage", rng),
            ],
            "cardiovascular"
        )

        # Respiratory system
        lung_tissue = Tissue("بافت ریه", "epithelial", 60, rng)
        airway_tissue = Tissue("مجارای تنفسی", "epithelial", 20, rng)
        self.respiratory_system = OrganSystem(
            "سیستم تنفسی",
            [
                Organ("ریه‌ها", [lung_tissue], "gas_exchange", rng),
                Organ("مجارای تنفسی", [airway_tissue], "airflow", rng),
            ],
            "respiratory"
        )

        # Digestive system
        stomach_tissue = Tissue("معده", "smooth_muscle", 40, rng)
        intestine_tissue = Tissue("روده", "epithelial", 60, rng)
        liver_tissue = Tissue("کبد", "hepatocyte", 70, rng)
        self.digestive_system = OrganSystem(
            "سیستم گوارشی",
            [
                Organ("معده", [stomach_tissue], "digestion", rng),
                Organ("روده", [intestine_tissue], "absorption", rng),
                Organ("کبد", [liver_tissue], "metabolism", rng),
            ],
            "digestive"
        )

        # Musculoskeletal system
        muscle_tissue = Tissue("عضلات", "skeletal_muscle", 80, rng)
        bone_tissue = Tissue("استخوان", "osteocyte", 40, rng)
        joint_tissue = Tissue("مفاصل", "cartilage", 20, rng)
        self.musculoskeletal_system = OrganSystem(
            "سیستم حرکتی",
            [
                Organ("عضلات", [muscle_tissue], "movement", rng),
                Organ("استخوان‌ها", [bone_tissue], "structure", rng),
                Organ("مفاصل", [joint_tissue], "flexibility", rng),
            ],
            "musculoskeletal"
        )

        # Immune system
        immune_tissue = Tissue("گلبول‌های سفید", "immune_cell", 50, rng)
        lymph_tissue = Tissue("سیستم لنفاوی", "lymphocyte", 30, rng)
        self.immune_system = OrganSystem(
            "سیستم ایمنی",
            [
                Organ("ایمنی ذاتی", [immune_tissue], "defense", rng),
                Organ("ایمنی تطبیقی", [lymph_tissue], "adaptation", rng),
            ],
            "immune"
        )

        # Endocrine system
        gland_tissue = Tissue("غدد", "endocrine_cell", 40, rng)
        self.endocrine_system = OrganSystem(
            "سیستم غدد",
            [
                Organ("غدد درون‌ریز", [gland_tissue], "hormone_production", rng),
            ],
            "endocrine"
        )

        # Urinary system
        kidney_tissue = Tissue("کلیه", "nephron", 50, rng)
        self.urinary_system = OrganSystem(
            "سیستم ادراری",
            [
                Organ("کلیه‌ها", [kidney_tissue], "filtration", rng),
            ],
            "urinary"
        )

        # Integumentary system (skin)
        skin_tissue = Tissue("پوست", "epithelial", 60, rng)
        self.integumentary_system = OrganSystem(
            "سیستم پوششی",
            [
                Organ("پوست", [skin_tissue], "protection", rng),
            ],
            "integumentary"
        )

        self.all_systems = [
            self.nervous_system,
            self.cardiovascular_system,
            self.respiratory_system,
            self.digestive_system,
            self.musculoskeletal_system,
            self.immune_system,
            self.endocrine_system,
            self.urinary_system,
            self.integumentary_system,
        ]

    def tick(self, brain_commands):
        """
        یک تیک کامل بدن با دستورات مغز.
        """
        # Apply brain commands
        self.neural_commands = brain_commands

        # Respiratory: oxygen intake
        breathing_rate = brain_commands.get("breathing_rate", 14)
        lung_function = self.respiratory_system.function / 100
        oxygen_gain = breathing_rate * 0.5 * lung_function
        self.oxygen = clamp100(self.oxygen + oxygen_gain - 2.0)

        # Cardiovascular: distribute oxygen and nutrients
        heart_rate = brain_commands.get("heart_rate", 70)
        heart_function = self.cardiovascular_system.function / 100
        distribution = heart_rate * 0.01 * heart_function

        # Digestive: nutrient absorption
        digestion = brain_commands.get("digestion", 0.5)
        digestive_function = self.digestive_system.function / 100
        nutrient_gain = digestion * 3.0 * digestive_function
        self.nutrients = clamp100(self.nutrients + nutrient_gain - 1.5)

        # Urinary: waste removal
        kidney_function = self.urinary_system.function / 100
        waste_removal = 2.0 * kidney_function
        self.waste = clamp100(self.waste - waste_removal + 1.0)

        # Hormone updates
        stress_hormone = self.stress / 100
        self.hormones["adrenaline"] = clamp100(20 + stress_hormone * 60 + brain_commands.get("alertness", 0.5) * 20)
        self.hormones["cortisol"] = clamp100(30 + stress_hormone * 50)
        self.hormones["dopamine"] = clamp100(self.hormones["dopamine"] + random.uniform(-2, 2))

        # Update all systems
        neural_signal = brain_commands.get("alertness", 0.5)
        hormonal_signal = self.hormones["adrenaline"] / 100

        for system in self.all_systems:
            system.tick(
                self.oxygen,
                self.nutrients,
                self.waste,
                neural_signal,
                hormonal_signal
            )

        # Body-wide state updates
        self.energy = clamp100(self.nutrients * 0.6 + self.oxygen * 0.3 - self.fatigue * 0.1)
        self.stress = clamp100(self.stress + self.hormones["cortisol"] * 0.1 - 0.5)
        self.fatigue = clamp100(self.fatigue + 0.2 - (1 if brain_commands.get("rest", False) else 0) * 1.5)
        self.pain = clamp100(self.pain + random.uniform(-0.5, 0.5))

        # Temperature regulation
        muscle_activity = brain_commands.get("muscle_tension", 0.3)
        self.temperature = clamp(36.5 + muscle_activity * 1.5 + self.stress * 0.01, 35, 42)

    def body_report(self):
        """
        گزارش یکپارچه بدن برای مغز.
        """
        return {
            "oxygen": self.oxygen,
            "nutrients": self.nutrients,
            "waste": self.waste,
            "energy": self.energy,
            "stress": self.stress,
            "pain": self.pain,
            "fatigue": self.fatigue,
            "temperature": self.temperature,
            "heart_rate": self.neural_commands.get("heart_rate", 70),
            "system_health": {s.name: s.health for s in self.all_systems},
            "system_function": {s.name: s.function for s in self.all_systems},
            "hormones": dict(self.hormones),
        }

    @property
    def total_cells(self):
        total = 0
        for system in self.all_systems:
            for organ in system.organs:
                for tissue in organ.tissues:
                    total += tissue.population.alive_count
        return total

    @property
    def overall_health(self):
        if not self.all_systems: return 50
        return sum(s.health for s in self.all_systems) / len(self.all_systems)


# ============================================================
# LEVEL 6: NEURAL BRAIN (Decision Center)
# ============================================================

class NeuralBrain:
    """
    مغز یکپارچه‌کننده: تصمیم‌گیری بر اساس کل بدن.
    """
    def __init__(self, rng):
        self.rng = rng
        self.regions = {
            "prefrontal": 0.5,
            "motor": 0.4,
            "sensory": 0.5,
            "limbic": 0.5,
            "brainstem": 0.7,
            "cerebellum": 0.5,
            "hippocampus": 0.5,
            "amygdala": 0.4,
        }
        self.consciousness = 40.0
        self.attention = 0.5
        self.emotion = {"valence": 0.2, "arousal": 0.4, "label": "متعادل"}
        self.working_memory = deque(maxlen=12)
        self.decision_log = deque(maxlen=30)

    def process_body_report(self, body_report):
        """
        پردازش گزارش بدن و تولید دستورات.
        """
        oxygen = body_report["oxygen"]
        energy = body_report["energy"]
        stress = body_report["stress"]
        fatigue = body_report["fatigue"]
        pain = body_report["pain"]

        # Determine body needs
        needs_urgent = []
        if oxygen < 50: needs_urgent.append("breathe_more")
        if energy < 30: needs_urgent.append("seek_food")
        if stress > 70: needs_urgent.append("reduce_stress")
        if fatigue > 70: needs_urgent.append("rest")
        if pain > 50: needs_urgent.append("avoid_damage")

        # Generate brain commands based on unified body state
        commands = {}

        # Heart rate regulation
        if oxygen < 60 or stress > 60:
            commands["heart_rate"] = clamp(70 + stress * 0.5, 60, 150)
        elif fatigue > 60:
            commands["heart_rate"] = clamp(60 + fatigue * 0.2, 50, 90)
        else:
            commands["heart_rate"] = 70 + random.uniform(-5, 5)

        # Breathing regulation
        if oxygen < 60:
            commands["breathing_rate"] = clamp(14 + (60 - oxygen) * 0.3, 12, 30)
        else:
            commands["breathing_rate"] = 14 + random.uniform(-2, 2)

        # Digestion
        if energy < 40:
            commands["digestion"] = 0.8
        else:
            commands["digestion"] = 0.4 + random.uniform(-0.1, 0.1)

        # Muscle tension
        if stress > 60 or pain > 40:
            commands["muscle_tension"] = 0.6
        else:
            commands["muscle_tension"] = 0.3 + random.uniform(-0.1, 0.1)

        # Alertness
        if fatigue > 70:
            commands["alertness"] = 0.3
        elif stress > 50:
            commands["alertness"] = 0.8
        else:
            commands["alertness"] = 0.5 + random.uniform(-0.1, 0.1)

        # Rest flag
        commands["rest"] = fatigue > 65

        # Update brain regions
        self.regions["brainstem"] = clamp(0.5 + oxygen / 200)
        self.regions["limbic"] = clamp(0.3 + stress / 200 + pain / 300)
        self.regions["prefrontal"] = clamp(0.4 + energy / 300 - fatigue / 300)
        self.regions["amygdala"] = clamp(0.2 + stress / 150)
        self.regions["hippocampus"] = clamp(0.4 + energy / 300)

        # Update consciousness
        self.consciousness = clamp100(
            self.regions["prefrontal"] * 30
            + self.regions["brainstem"] * 25
            + (1 - fatigue / 100) * 20
            + oxygen / 100 * 15
            + self.attention * 10
        )

        # Update emotion
        self.emotion["valence"] = clamp((energy - stress - pain) / 150, -1, 1)
        self.emotion["arousal"] = clamp(stress / 100 * 0.6 + (1 - fatigue / 100) * 0.4)

        v = self.emotion["valence"]
        a = self.emotion["arousal"]
        if v > 0.3: self.emotion["label"] = "خوشایند" if a > 0.5 else "آرام"
        elif v < -0.3: self.emotion["label"] = "ناخوشایند" if a > 0.5 else "خسته"
        else: self.emotion["label"] = "متعادل"

        # Working memory
        self.working_memory.append({
            "time": now_hms(),
            "needs": needs_urgent,
            "consciousness": self.consciousness,
            "emotion": self.emotion["label"],
        })

        # Decision
        action = self._decide(needs_urgent, body_report)
        self.decision_log.append({
            "time": now_hms(),
            "action": action,
            "reason": needs_urgent if needs_urgent else ["تعادل"],
        })

        return commands, action

    def _decide(self, needs, body_report):
        """
        تصمیم متحد بر اساس نیازهای بدن.
        """
        if "avoid_damage" in needs: return "محافظت از بدن"
        if "breathe_more" in needs: return "افزایش تنفس"
        if "seek_food" in needs: return "جستجوی غذا"
        if "reduce_stress" in needs: return "کاهش استرس"
        if "rest" in needs: return "استراحت"

        # If no urgent needs, choose based on brain state
        if self.regions["prefrontal"] > 0.6:
            return "برنامه‌ریزی و یادگیری"
        elif self.regions["limbic"] > 0.6:
            return "پردازش احساسی"
        else:
            return "حفظ تعادل"

    def generate_inner_speech(self, body_report):
        """
        تولید گفتار درونی بر اساس وضعیت بدن.
        """
        oxygen = body_report["oxygen"]
        energy = body_report["energy"]
        stress = body_report["stress"]
        fatigue = body_report["fatigue"]

        if oxygen < 50:
            return "نیاز به اکسیژن بیشتر دارم. باید عمیق‌تر نفس بکشم."
        if energy < 30:
            return "انرژی بدنم کم است. باید تغذیه کنم."
        if stress > 70:
            return "استرس بدنم بالاست. باید آرام شوم."
        if fatigue > 70:
            return "خسته‌ام. باید استراحت کنم."

        if self.emotion["valence"] > 0.3:
            return "حالم خوب است. بدنم متعادل کار می‌کند."
        elif self.emotion["valence"] < -0.3:
            return "حالم خوب نیست. باید به بدنم توجه کنم."
        else:
            return "در تعادل هستم. بدنم یکپارچه عمل می‌کند."


# ============================================================
# LEVEL 7: UNIFIED ORGANISM (AGI Core)
# ============================================================

class UnifiedOrganism:
    """
    ارگانیزم یکپارچه: بدن + مغز + تصمیم‌گیری متحد.
    """
    def __init__(self):
        self.rng = random.Random(int(time.time() * 1000))
        self.body = HumanBody(self.rng)
        self.brain = NeuralBrain(self.rng)

        self.age = 0
        self.current_action = "حفظ تعادل"
        self.inner_speech = ""
        self.logs = deque(maxlen=80)
        self.action_history = deque(maxlen=30)

        self.add_log("تولد", "ارگانیزم یکپارچه بیدار شد.")

    def add_log(self, kind, text):
        self.logs.append({
            "time": now_hms(),
            "kind": kind,
            "text": text,
        })

    def tick(self):
        try:
            self.age += 1

            # 1. Brain receives body report
            body_report = self.body.body_report()

            # 2. Brain processes and generates commands
            commands, action = self.brain.process_body_report(body_report)

            # 3. Body executes brain commands
            self.body.tick(commands)

            # 4. Update organism state
            self.current_action = action
            self.inner_speech = self.brain.generate_inner_speech(body_report)

            # 5. Log significant events
            if self.age % 5 == 0:
                self.action_history.append({
                    "time": now_hms(),
                    "action": action,
                    "consciousness": self.brain.consciousness,
                })

            if self.age % 20 == 0:
                self.add_log("وضعیت", f"آگاهی: {self.brain.consciousness:.0f}% | عمل: {action}")

            if self.body.overall_health < 40 and self.age % 10 == 0:
                self.add_log("هشدار", "سلامت بدن در خطر است.")

        except Exception as e:
            self.add_log("خطا", f"خطای سیستمی: {str(e)[:60]}")

    def get_body_systems_summary(self):
        return {
            s.name: {"health": s.health, "function": s.function}
            for s in self.body.all_systems
        }


# ============================================================
# RENDERING
# ============================================================

PAGE_BG = "#05080d"
CARD_BG = "#0b1220"
TEXT_COLOR = "#d7e7ff"
ACCENT = "#00ff88"

CARD_STYLE = {
    "backgroundColor": CARD_BG,
    "border": "1px solid #1b2a44",
    "borderRadius": "12px",
    "padding": "12px",
}


def base_fig(title="", height=250):
    fig = go.Figure()
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=CARD_BG,
        plot_bgcolor=CARD_BG,
        font={"color": TEXT_COLOR, "size": 11},
        margin=dict(l=30, r=10, t=38, b=10),
        height=height,
        title=title,
    )
    return fig


def render_header(org):
    body = org.body
    brain = org.brain

    return html.Div(style={"display": "flex", "gap": "16px", "flexWrap": "wrap"}, children=[
        html.Span("🧬 ارگانیزم یکپارچه", style={"color": ACCENT, "fontWeight": "bold"}),
        html.Span(f"سن: {org.age}"),
        html.Span(f"آگاهی: {brain.consciousness:.0f}%"),
        html.Span(f"سلامت بدن: {body.overall_health:.0f}%"),
        html.Span(f"سلول‌ها: {body.total_cells}"),
        html.Span(f"عمل فعلی: {org.current_action}"),
        html.Span(f"احساس: {brain.emotion['label']}"),
    ])


def vital_card(title, value, sub, color="#7fd4ff"):
    return html.Div(style={
        **CARD_STYLE,
        "display": "flex",
        "flexDirection": "column",
        "gap": "3px",
        "minHeight": "84px",
    }, children=[
        html.Div(title, style={"color": "#8aa0b8", "fontSize": "11px"}),
        html.Div(value, style={"color": color, "fontSize": "17px", "fontWeight": "bold"}),
        html.Div(sub, style={"color": "#7d93aa", "fontSize": "10px"}),
    ])


def render_vitals(org):
    body = org.body
    brain = org.brain

    return [
        vital_card("آگاهی", f"{brain.consciousness:.0f}%", f"توجه: {brain.attention*100:.0f}%", "#00e5ff"),
        vital_card("انرژی", f"{body.energy:.0f}%", f"مواد مغذی: {body.nutrients:.0f}%", "#ffd166"),
        vital_card("اکسیژن", f"{body.oxygen:.0f}%", f"تنفس: {body.neural_commands.get('breathing_rate', 14):.0f}", "#8be9fd"),
        vital_card("استرس", f"{body.stress:.0f}%", f"کورتیزول: {body.hormones['cortisol']:.0f}", "#ff9f43"),
        vital_card("خستگی", f"{body.fatigue:.0f}%", f"دما: {body.temperature:.1f}°C", "#ff5f7a"),
        vital_card("درد", f"{body.pain:.0f}%", f"ایمنی: {body.immune_activity:.0f}%", "#ff8bd0"),
        vital_card("سلول‌ها", f"{body.total_cells}", "جمعیت زنده", ACCENT),
        vital_card("احساس", brain.emotion["label"], f"V:{brain.emotion['valence']:+.2f} A:{brain.emotion['arousal']:.2f}", "#b388ff"),
    ]


def render_body_systems(org):
    fig = base_fig("سلامت سیستم‌های بدن", height=350)

    systems = org.get_body_systems_summary()
    names = list(systems.keys())
    health = [systems[n]["health"] for n in names]
    function = [systems[n]["function"] for n in names]

    fig.add_trace(go.Bar(name="سلامت", x=names, y=health, marker_color="#00ff88"))
    fig.add_trace(go.Bar(name="عملکرد", x=names, y=function, marker_color="#00e5ff"))

    fig.update_layout(barmode="group")
    fig.update_yaxes(range=[0, 100])
    fig.update_xaxes(tickangle=45)

    return fig


def render_brain_regions(org):
    fig = base_fig("فعالیت مناطق مغز", height=300)

    regions = org.brain.regions
    names = list(regions.keys())
    values = list(regions.values())

    fig.add_trace(go.Bar(x=names, y=values, marker_color="#b388ff"))
    fig.update_yaxes(range=[0, 1])
    fig.update_xaxes(tickangle=45)

    return fig


def render_hormones(org):
    fig = base_fig("سطح هورمون‌ها", height=300)

    hormones = org.body.hormones
    names = list(hormones.keys())
    values = list(hormones.values())

    colors = []
    for name in names:
        if name in ["adrenaline", "cortisol"]:
            colors.append("#ff5f7a")
        elif name in ["serotonin", "dopamine"]:
            colors.append("#00ff88")
        else:
            colors.append("#ffd166")

    fig.add_trace(go.Bar(x=names, y=values, marker_color=colors))
    fig.update_yaxes(range=[0, 100])
    fig.update_xaxes(tickangle=45)

    return fig


def render_consciousness_timeline(org):
    fig = base_fig("مسیر آگاهی و تصمیمات", height=300)

    history = list(org.action_history)
    if not history:
        fig.add_annotation(text="هنوز داده‌ای نیست", x=0, y=0, showarrow=False)
        return fig

    times = list(range(len(history)))
    consciousness = [h["consciousness"] for h in history]
    actions = [h["action"] for h in history]

    fig.add_trace(go.Scatter(
        x=times,
        y=consciousness,
        mode="lines+markers",
        line=dict(color="#00e5ff", width=2),
        name="آگاهی"
    ))

    return fig


def render_inner_speech(org):
    children = []

    children.append(html.Div(style={
        "borderLeft": "3px solid #00e5ff",
        "padding": "8px 12px",
        "marginBottom": "8px",
        "backgroundColor": "#08101c",
        "borderRadius": "8px",
        "fontSize": "13px",
        "lineHeight": "1.8",
    }, children=[
        html.Div("💭 گفتار درونی:", style={"color": "#ffd166", "fontSize": "11px", "marginBottom": "4px"}),
        html.Div(org.inner_speech, style={"color": "#e0e0ff"}),
    ]))

    # Working memory
    wm_items = list(org.brain.working_memory)[-6:][::-1]
    for item in wm_items:
        needs_str = ", ".join(item["needs"]) if item["needs"] else "بدون نیاز فوری"
        children.append(html.Div(style={
            "borderLeft": "3px solid #b388ff",
            "padding": "5px 8px",
            "marginBottom": "6px",
            "backgroundColor": "#08101c",
            "borderRadius": "6px",
            "fontSize": "11px",
        }, children=[
            html.Span(item["time"], style={"color": "#64748b", "fontSize": "9px"}),
            html.Br(),
            html.Span(f"نیازها: {needs_str} | آگاهی: {item['consciousness']:.0f}%"),
        ]))

    return html.Div([
        html.H4("🧠 ذهن یکپارچه", style={"margin": "0 0 8px 0", "color": "#00e5ff"}),
        html.Div(children, style={"height": "350px", "overflowY": "auto"}),
    ])


def render_decision_log(org):
    items = list(org.brain.decision_log)[-15:][::-1]
    children = []

    if not items:
        children.append(html.Div("هنوز تصمیمی ثبت نشده.", style={"color": "#64748b"}))
    else:
        for item in items:
            reason_str = ", ".join(item["reason"]) if item["reason"] else "تعادل"
            children.append(html.Div(style={
                "borderLeft": "3px solid #ff9f43",
                "padding": "5px 8px",
                "marginBottom": "6px",
                "backgroundColor": "#08101c",
                "borderRadius": "6px",
                "fontSize": "11px",
            }, children=[
                html.Span(item["time"], style={"color": "#64748b", "fontSize": "9px"}),
                html.Br(),
                html.Span(f"عمل: {item['action']} | دلیل: {reason_str}"),
            ]))

    return html.Div([
        html.H4("⚡ تصمیمات متحد", style={"margin": "0 0 8px 0", "color": "#ff9f43"}),
        html.Div(children, style={"height": "350px", "overflowY": "auto"}),
    ])


def render_logs(org):
    items = list(org.logs)[-18:][::-1]
    children = []

    if not items:
        children.append(html.Div("...", style={"color": "#64748b"}))
    else:
        for item in items:
            children.append(html.Div(style={
                "borderLeft": "3px solid #9fd0ff",
                "padding": "5px 8px",
                "marginBottom": "6px",
                "backgroundColor": "#08101c",
                "borderRadius": "6px",
                "fontSize": "11px",
            }, children=[
                html.Span(item["time"], style={"color": "#64748b", "fontSize": "9px"}),
                html.Br(),
                html.Span(f"{item['kind']}: {item['text']}"),
            ]))

    return html.Div([
        html.H4("🌱 جریان حیات", style={"margin": "0 0 8px 0", "color": "#9fd0ff"}),
        html.Div(children, style={"height": "320px", "overflowY": "auto"}),
    ])


def safe_fig(fn, org, title):
    try:
        return fn(org)
    except Exception:
        fig = base_fig(title, height=250)
        fig.add_annotation(text="خطا در رندر", x=0, y=0, showarrow=False, font=dict(color="#ff5555"))
        return fig


def safe_div(fn, org, fallback):
    try:
        return fn(org)
    except Exception as e:
        return html.Div(f"⚠ {fallback}: {str(e)[:60]}", style={"color": "#ff5555"})


# ============================================================
# DASH APP
# ============================================================

app = Dash(__name__)
app.title = "ارگانیزم یکپارچه بدن انسان"
app.config.suppress_callback_exceptions = True

ORGANISM = UnifiedOrganism()

app.layout = html.Div(style={
    "backgroundColor": PAGE_BG,
    "color": TEXT_COLOR,
    "minHeight": "100vh",
    "padding": "12px",
    "fontFamily": "Tahoma, Arial, sans-serif",
}, children=[

    dcc.Interval(id="life-interval", interval=1200, disabled=False),

    html.H1("🧬 ارگانیزم یکپارچه بدن انسان", style={
        "margin": "0 0 10px 0",
        "fontSize": "22px",
        "color": "#eaffff"
    }),

    html.Div(id="header-info", style={**CARD_STYLE, "marginBottom": "10px"}),

    html.Div(id="vital-cards", style={
        "display": "grid",
        "gridTemplateColumns": "repeat(auto-fit, minmax(150px, 1fr))",
        "gap": "8px",
        "marginBottom": "10px"
    }),

    # Body systems and brain
    html.Div(style={
        "display": "grid",
        "gridTemplateColumns": "1fr 1fr",
        "gap": "10px",
        "marginBottom": "10px"
    }, children=[
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="body-systems-graph", config={"displayModeBar": False})
        ]),
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="brain-regions-graph", config={"displayModeBar": False})
        ]),
    ]),

    # Hormones and consciousness
    html.Div(style={
        "display": "grid",
        "gridTemplateColumns": "1fr 1fr",
        "gap": "10px",
        "marginBottom": "10px"
    }, children=[
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="hormones-graph", config={"displayModeBar": False})
        ]),
        html.Div(style=CARD_STYLE, children=[
            dcc.Graph(id="consciousness-graph", config={"displayModeBar": False})
        ]),
    ]),

    # Mind, decisions, logs
    html.Div(style={
        "display": "grid",
        "gridTemplateColumns": "1fr 1fr 1fr",
        "gap": "10px",
        "marginBottom": "10px"
    }, children=[
        html.Div(id="mind-panel", style=CARD_STYLE),
        html.Div(id="decision-panel", style=CARD_STYLE),
        html.Div(id="logs-panel", style=CARD_STYLE),
    ]),

])


@app.callback(
    [
        Output("header-info", "children"),
        Output("vital-cards", "children"),
        Output("body-systems-graph", "figure"),
        Output("brain-regions-graph", "figure"),
        Output("hormones-graph", "figure"),
        Output("consciousness-graph", "figure"),
        Output("mind-panel", "children"),
        Output("decision-panel", "children"),
        Output("logs-panel", "children"),
    ],
    Input("life-interval", "n_intervals")
)
def update_life(n):
    try:
        ORGANISM.tick()
    except Exception as e:
        try:
            ORGANISM.add_log("خطا", f"خطای اصلی: {str(e)[:60]}")
        except Exception:
            pass

    return (
        safe_div(render_header, ORGANISM, "header"),
        safe_div(render_vitals, ORGANISM, "vitals"),
        safe_fig(render_body_systems, ORGANISM, "سیستم‌های بدن"),
        safe_fig(render_brain_regions, ORGANISM, "مغز"),
        safe_fig(render_hormones, ORGANISM, "هورمون‌ها"),
        safe_fig(render_consciousness_timeline, ORGANISM, "آگاهی"),
        safe_div(render_inner_speech, ORGANISM, "ذهن"),
        safe_div(render_decision_log, ORGANISM, "تصمیمات"),
        safe_div(render_logs, ORGANISM, "لاگ"),
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8050, debug=False, use_reloader=False, threaded=True)