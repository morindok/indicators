import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np
import os

desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
os.makedirs(desktop, exist_ok=True)

# ============================================================
# IMAGE 1: Main Dashboard with Charts
# ============================================================
fig1, axes = plt.subplots(2, 3, figsize=(20, 12))
fig1.suptitle('Quantum Digital Currency Analytics - Dashboard', 
              fontsize=20, fontweight='bold', color='#1a1a2e', y=0.98)

colors = {
    'primary': '#6C63FF',
    'secondary': '#FF6584',
    'accent': '#43E97B',
    'dark': '#1a1a2e',
    'light': '#f0f0f5',
    'cyan': '#00D2FF',
    'orange': '#FF9A3C'
}

# Chart 1: Price Candlestick-like chart
ax1 = axes[0, 0]
np.random.seed(42)
days = 60
base = 45000
prices = base + np.cumsum(np.random.randn(days) * 800)
opens = prices + np.random.randn(days) * 400
highs = np.maximum(prices, opens) + np.abs(np.random.randn(days) * 600)
lows = np.minimum(prices, opens) - np.abs(np.random.randn(days) * 600)

for i in range(days):
    color = '#43E97B' if prices[i] >= opens[i] else '#FF6584'
    ax1.plot([i, i], [lows[i], highs[i]], color=color, linewidth=0.8)
    ax1.plot([i, i], [min(opens[i], prices[i]), max(opens[i], prices[i])], 
             color=color, linewidth=3)

ax1.set_title('BTC/USDT Price Action', fontsize=12, fontweight='bold', color=colors['dark'])
ax1.set_xlabel('Days')
ax1.set_ylabel('Price (USDT)')
ax1.grid(True, alpha=0.3)
ax1.set_facecolor('#fafafa')

# Chart 2: Quantum Signal Strength
ax2 = axes[0, 1]
signal_x = np.linspace(0, 2*np.pi, 100)
signal_y1 = np.sin(signal_x) * 0.8 + np.random.randn(100) * 0.05
signal_y2 = np.cos(signal_x * 1.5) * 0.6 + np.random.randn(100) * 0.05
signal_y3 = np.sin(signal_x * 2.5) * 0.4 + np.random.randn(100) * 0.05

ax2.fill_between(signal_x, signal_y1, alpha=0.3, color=colors['primary'])
ax2.plot(signal_x, signal_y1, color=colors['primary'], linewidth=2, label='Q-Bit Alpha')
ax2.plot(signal_x, signal_y2, color=colors['secondary'], linewidth=2, label='Q-Bit Beta')
ax2.plot(signal_x, signal_y3, color=colors['accent'], linewidth=2, label='Q-Bit Gamma')
ax2.axhline(y=0, color='gray', linestyle='--', linewidth=0.8)
ax2.set_title('Quantum Signal Oscillator', fontsize=12, fontweight='bold', color=colors['dark'])
ax2.legend(fontsize=8)
ax2.grid(True, alpha=0.3)
ax2.set_facecolor('#fafafa')

# Chart 3: Portfolio Allocation Pie
ax3 = axes[0, 2]
sizes = [35, 25, 18, 12, 10]
labels = ['BTC', 'ETH', 'SOL', 'ADA', 'Others']
explode = (0.05, 0.02, 0.02, 0.02, 0.02)
wedges, texts, autotexts = ax3.pie(sizes, explode=explode, labels=labels,
                                    autopct='%1.1f%%', startangle=90,
                                    colors=[colors['primary'], colors['secondary'],
                                            colors['accent'], colors['cyan'], colors['orange']])
for text in texts:
    text.set_fontsize(10)
for autotext in autotexts:
    autotext.set_fontsize(9)
    autotext.set_color('white')
ax3.set_title('Portfolio Allocation', fontsize=12, fontweight='bold', color=colors['dark'])

# Chart 4: Volume Bar Chart
ax4 = axes[1, 0]
volume_data = np.random.randint(100, 1000, 30)
bar_colors = [colors['accent'] if volume_data[i] > 500 else colors['primary'] for i in range(30)]
ax4.bar(range(30), volume_data, color=bar_colors, alpha=0.8)
ax4.set_title('Trading Volume (24h Rolling)', fontsize=12, fontweight='bold', color=colors['dark'])
ax4.set_xlabel('Time Windows')
ax4.set_ylabel('Volume (M USDT)')
ax4.grid(True, alpha=0.3, axis='y')
ax4.set_facecolor('#fafafa')

# Chart 5: Fear & Greed Index Gauge
ax5 = axes[1, 1]
theta = np.linspace(0, np.pi, 100)
r = np.ones_like(theta)
ax5 = fig1.add_subplot(2, 3, 5, projection='polar')
ax5.set_theta_zero_location('W')
ax5.set_theta_direction(1)

# Color gradient for gauge
gradient_colors = plt.cm.RdYlGn(np.linspace(0.15, 0.85, 100))
for i in range(99):
    ax5.plot(theta[i:i+2], [0.9, 0.9], color=gradient_colors[i], linewidth=15, solid_capstyle='round')

# Needle at "Greed" position (65/100)
needle_angle = np.pi * 0.35
ax5.annotate('', xy=(needle_angle, 0.85), xytext=(0, 0),
            arrowprops=dict(arrowstyle='->', color=colors['dark'], lw=3))
ax5.set_ylim(0, 1.1)
ax5.set_yticklabels([])
ax5.set_xticks([0, np.pi/4, np.pi/2, 3*np.pi/4, np.pi])
ax5.set_xticklabels(['Fear', 'Anxiety', 'Neutral', 'Greed', 'Euphoria'], fontsize=8)
ax5.set_title('Fear & Greed Index: 65 (Greed)', fontsize=12, fontweight='bold', 
              color=colors['dark'], pad=20)

# Chart 6: Risk Heatmap
ax6 = axes[1, 2]
risk_data = np.random.rand(7, 5)
im = ax6.imshow(risk_data, cmap='RdYlGn_r', aspect='auto', vmin=0, vmax=1)
ax6.set_xticks(range(5))
ax6.set_xticklabels(['Vol', 'Liq', 'Mom', 'Sent', 'Quant'], fontsize=9)
ax6.set_yticks(range(7))
ax6.set_yticklabels(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'], fontsize=9)
for i in range(7):
    for j in range(5):
        ax6.text(j, i, f'{risk_data[i, j]:.2f}', ha='center', va='center', fontsize=8, color='white')
plt.colorbar(im, ax=ax6, shrink=0.8)
ax6.set_title('Multi-Factor Risk Heatmap', fontsize=12, fontweight='bold', color=colors['dark'])

plt.tight_layout(rect=[0, 0, 1, 0.95])
path1 = os.path.join(desktop, 'quantum_crypto_dashboard.png')
fig1.savefig(path1, dpi=200, bbox_inches='tight', facecolor='white')
plt.close(fig1)
print(f"Image 1 saved: {path1}")

# ============================================================
# IMAGE 2: System Architecture Diagram
# ============================================================
fig2, ax = plt.subplots(1, 1, figsize=(22, 14))
ax.set_xlim(0, 100)
ax.set_ylim(0, 70)
ax.axis('off')
ax.set_facecolor('#f8f9ff')

# Title
ax.text(50, 67, 'Quantum Digital Currency Analytics System Architecture',
        fontsize=22, fontweight='bold', ha='center', va='center', color='#1a1a2e')
ax.text(50, 65.5, 'Microservice-Based Quantum Computing Integration for Real-Time Crypto Analysis',
        fontsize=11, ha='center', va='center', color='#555')

def draw_box(ax, x, y, w, h, text, color, fontsize=10, subtext=None):
    box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3",
                          facecolor=color, edgecolor='#333', linewidth=1.5, alpha=0.9)
    ax.add_patch(box)
    if subtext:
        ax.text(x + w/2, y + h/2 + 0.3, text, fontsize=fontsize, fontweight='bold',
                ha='center', va='center', color='white')
        ax.text(x + w/2, y + h/2 - 0.5, subtext, fontsize=fontsize-3,
                ha='center', va='center', color='#ddd')
    else:
        ax.text(x + w/2, y + h/2, text, fontsize=fontsize, fontweight='bold',
                ha='center', va='center', color='white')

def draw_section(ax, x, y, w, h, title, color_edge, color_bg='#f0f4ff'):
    rect = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.5",
                           facecolor=color_bg, edgecolor=color_edge, linewidth=2, alpha=0.6)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h - 0.8, title, fontsize=12, fontweight='bold',
            ha='center', va='center', color=color_edge)

def draw_arrow(ax, x1, y1, x2, y2, color='#555', style='->', lw=1.5):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
               arrowprops=dict(arrowstyle=style, color=color, lw=lw, connectionstyle='arc3,rad=0.1'))

# === LAYER 1: Data Sources (Top) ===
draw_section(ax, 1, 54.5, 98, 10, 'DATA SOURCE LAYER', '#2196F3', '#e3f2fd')

sources = [('Binance API', 8), ('CoinBase API', 22), ('Kraken API', 36), 
           ('On-Chain Data', 50), ('Social Sentiment', 64), ('News Feed', 78)]
for name, x in sources:
    draw_box(ax, x, 56, 12, 5, name, '#2196F3', 9)

draw_box(ax, 88, 56, 9, 5, 'WebSocket\nStreams', '#1565C0', 8)

# === LAYER 2: Ingestion & Stream Processing ===
draw_section(ax, 1, 42, 98, 10, 'INGESTION & STREAM PROCESSING LAYER', '#FF9800', '#fff3e0')

draw_box(ax, 5, 43.5, 14, 5, 'Apache Kafka\nCluster', '#FF9800', 9)
draw_box(ax, 22, 43.5, 14, 5, 'Apache Flink\nStream Engine', '#E65100', 9)
draw_box(ax, 39, 43.5, 14, 5, 'Data Validator\n& Normalizer', '#F57C00', 9)
draw_box(ax, 56, 43.5, 14, 5, 'Feature\nEngineer', '#FFA726', 9)
draw_box(ax, 73, 43.5, 12, 5, 'Redis Cache\nLayer', '#D84315', 9)
draw_box(ax, 88, 43.5, 9, 5, 'Time Series\nDB', '#BF360C', 9)

# === LAYER 3: Quantum Computing Core ===
draw_section(ax, 1, 27, 98, 12, 'QUANTUM COMPUTING CORE', '#9C27B0', '#f3e5f5')

draw_box(ax, 4, 28.5, 16, 6, 'Quantum Processor\nInterface', '#7B1FA2', 9, 'Qiskit / Cirq')
draw_box(ax, 23, 28.5, 16, 6, 'Quantum Monte Carlo\nSimulator', '#6A1B9A', 9, 'Price Forecasting')
draw_box(ax, 42, 28.5, 16, 6, 'Quantum Optimization\nEngine', '#4A148C', 9, 'Portfolio Optimization')
draw_box(ax, 61, 28.5, 16, 6, 'Quantum ML\nClassifier', '#8E24AA', 9, 'Pattern Recognition')
draw_box(ax, 80, 28.5, 17, 6, 'Quantum Random\nNumber Generator', '#9C27B0', 9, 'Risk Simulation')

# === LAYER 4: Classical Analytics ===
draw_section(ax, 1, 14, 48, 10.5, 'CLASSICAL ANALYTICS ENGINE', '#4CAF50', '#e8f5e9')

draw_box(ax, 3, 15.5, 11, 4.5, 'Technical\nIndicators', '#388E3C', 9)
draw_box(ax, 16, 15.5, 11, 4.5, 'Sentiment\nAnalyzer (NLP)', '#2E7D32', 9)
draw_box(ax, 29, 15.5, 9, 4.5, 'Risk\nModel', '#43A047', 9)
draw_box(ax, 40, 15.5, 8, 4.5, 'Backtest\nEngine', '#66BB6A', 9)

# === LAYER 5: API & Dashboard ===
draw_section(ax, 51, 14, 48, 10.5, 'API & PRESENTATION LAYER', '#00BCD4', '#e0f7fa')

draw_box(ax, 53, 15.5, 11, 4.5, 'REST / GraphQL\nAPI Gateway', '#00838F', 9)
draw_box(ax, 66, 15.5, 11, 4.5, 'Web Dashboard\n(React/Vue)', '#006064', 9)
draw_box(ax, 79, 15.5, 9, 4.5, 'Mobile App\n(React Native)', '#0097A7', 9)
draw_box(ax, 90, 15.5, 8, 4.5, 'Alert\nSystem', '#00ACC1', 9)

# === LAYER 6: Infrastructure (Bottom) ===
draw_section(ax, 1, 1, 98, 11, 'INFRASTRUCTURE & DEPLOYMENT', '#607D8B', '#eceff1')

draw_box(ax, 3, 2.5, 12, 5, 'Kubernetes\nCluster', '#37474F', 9)
draw_box(ax, 17, 2.5, 12, 5, 'Docker\nContainers', '#455A64', 9)
draw_box(ax, 31, 2.5, 12, 5, 'Prometheus\n+ Grafana', '#546E7A', 9, 'Monitoring')
draw_box(ax, 45, 2.5, 12, 5, 'PostgreSQL\n+ TimescaleDB', '#4E342E', 9)
draw_box(ax, 59, 2.5, 12, 5, 'MongoDB\nCluster', '#3E2723', 9)
draw_box(ax, 73, 2.5, 12, 5, 'AWS / GCP\nCloud', '#1565C0', 9)
draw_box(ax, 87, 2.5, 10, 5, 'CI/CD\nPipeline', '#283593', 9)

# === Arrows connecting layers ===
# Data Sources -> Ingestion
for x in [14, 28, 42, 56, 70, 84]:
    draw_arrow(ax, x, 56, x, 49, '#2196F3', lw=1.2)

# Ingestion -> Quantum
for x in [12, 29, 46, 63, 80]:
    draw_arrow(ax, x, 43.5, x, 34.5, '#FF9800', lw=1.2)

# Ingestion -> Classical
draw_arrow(ax, 10, 43.5, 10, 20, '#4CAF50', lw=1.2)
draw_arrow(ax, 22, 43.5, 22, 20, '#4CAF50', lw=1.2)

# Quantum -> API
draw_arrow(ax, 48, 28.5, 58, 20, '#9C27B0', lw=1.5)
draw_arrow(ax, 58, 28.5, 70, 20, '#9C27B0', lw=1.5)

# Classical -> API
draw_arrow(ax, 44, 17.5, 53, 17.5, '#4CAF50', lw=1.5)

# API -> Infrastructure
for x in [58, 72, 84]:
    draw_arrow(ax, x, 15.5, x, 8, '#607D8B', lw=1)

# Legend
legend_items = [
    ('#2196F3', 'Data Sources'),
    ('#FF9800', 'Stream Processing'),
    ('#9C27B0', 'Quantum Computing'),
    ('#4CAF50', 'Classical Analytics'),
    ('#00BCD4', 'API & UI'),
    ('#607D8B', 'Infrastructure')
]
for i, (color, label) in enumerate(legend_items):
    ax.add_patch(FancyBboxPatch((2 + i*16, 0.3), 1.5, 0.8, boxstyle="round,pad=0.1",
                                 facecolor=color, edgecolor='#333', linewidth=0.8))
    ax.text(3.8 + i*16, 0.7, label, fontsize=7.5, ha='left', va='center', color='#333')

path2 = os.path.join(desktop, 'quantum_system_architecture.png')
fig2.savefig(path2, dpi=200, bbox_inches='tight', facecolor='#f8f9ff')
plt.close(fig2)
print(f"Image 2 saved: {path2}")
print("\nDone! Both images saved to Desktop.")
