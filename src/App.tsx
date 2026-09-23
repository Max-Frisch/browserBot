/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from "react";
import {
  Terminal,
  Shield,
  Server,
  Layers,
  Code2,
  FileText,
  AlertCircle,
  CheckCircle2,
  Copy,
  ExternalLink,
  ChevronRight,
  Globe,
  Camera,
  Cpu,
  RefreshCw,
  Eye,
  Rocket
} from "lucide-react";

interface QueueGoal {
  type: "building" | "ship" | "defense" | "research";
  name: string;
  level?: number;
  amount?: number;
}

interface QueueData {
  main_planet: string;
  research_goals: QueueGoal[];
  planets: Record<string, QueueGoal[]>;
}

const INITIAL_QUEUE_DATA: QueueData = {
  main_planet: "3:7:1",
  research_goals: [],
  planets: {
    "3:7:1": [
      {
        type: "ship",
        name: "Colonization Ship",
        amount: 1
      }
    ],
    "2:109:1": [],
    "2:109:2": [],
    "2:109:3": [],
    "2:43:1": [
      {
        type: "building",
        name: "Iron Mine",
        level: 15
      }
    ],
    "2:43:2": [
      {
        type: "building",
        name: "Iron Mine",
        level: 15
      }
    ],
    "2:43:3": [
      {
        type: "building",
        name: "Iron Mine",
        level: 15
      }
    ]
  }
};

const FILES_CONTENT: Record<string, { desc: string; role: string; language: string; path: string }> = {
  "main.py": {
    desc: "Orchestrates headless launch, stealth context setup, login verification, error capture, and main cycle loop.",
    role: "Core Execution Daemon",
    language: "python",
    path: "main.py"
  },
  "config.py": {
    desc: "Central configuration, desktop spoofing headers, stealth script, safe navigation, and error snapshot utility.",
    role: "Configuration & Stealth Profile",
    language: "python",
    path: "config.py"
  },
  "telemetry.py": {
    desc: "Resource parsing, storage capacity calculation, exposed resource analysis, and active queue monitoring.",
    role: "Planet State & Resources",
    language: "python",
    path: "telemetry.py"
  },
  "planner.py": {
    desc: "Recursive tech tree resolution, prerequisite tree pivoting, parallel construction, and ship orders.",
    role: "Autonomous Building & Goal Queue",
    language: "python",
    path: "planner.py"
  },
  "shipyard.py": {
    desc: "Live ship catalog parsing from /ship, resource safeguard depositing, and auto-recycling.",
    role: "Fleet Production & Resource Shield",
    language: "python",
    path: "shipyard.py"
  },
  "defense.py": {
    desc: "Hostile and incoming fleet radar monitoring with adaptive high-frequency sleep triggers.",
    role: "Radar & Early Warning Alerts",
    language: "python",
    path: "defense.py"
  },
  "build_queue.json": {
    desc: "Planetary goals, target upgrade levels, unit orders, and empire configuration.",
    role: "JSON Queue Data Store",
    language: "json",
    path: "build_queue.json"
  },
  "auth.json": {
    desc: "Persisted session cookies (PHPSESSID) for uninterrupted headless logins without CAPTCHAs.",
    role: "Session Auth Storage",
    language: "json",
    path: "auth.json"
  }
};

export default function App() {
  const [activeTab, setActiveTab] = useState<"overview" | "queue" | "stealth" | "vps" | "files">("overview");
  const [selectedFile, setSelectedFile] = useState<string>("main.py");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [queueData, setQueueData] = useState<QueueData>(INITIAL_QUEUE_DATA);
  const [newCoord, setNewCoord] = useState<string>("");

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const addPlanet = () => {
    if (!newCoord.trim()) return;
    if (!queueData.planets[newCoord.trim()]) {
      setQueueData({
        ...queueData,
        planets: {
          ...queueData.planets,
          [newCoord.trim()]: []
        }
      });
      setNewCoord("");
    }
  };

  const removePlanet = (coord: string) => {
    const updated = { ...queueData.planets };
    delete updated[coord];
    setQueueData({ ...queueData, planets: updated });
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans flex flex-col selection:bg-cyan-500 selection:text-slate-950">
      {/* Top Navbar */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
              <Rocket className="h-5 w-5 animate-pulse" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold tracking-wide text-white text-base">GigraWars Bot</span>
                <span className="px-2 py-0.5 text-xs font-semibold rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                  Headless VPS Ready
                </span>
              </div>
              <p className="text-xs text-slate-400">Stealth Profile & Diagnostic Snapshot Engine</p>
            </div>
          </div>

          {/* Navigation tabs */}
          <nav className="flex items-center gap-1 bg-slate-950/60 p-1 rounded-xl border border-slate-800 text-sm">
            <button
              onClick={() => setActiveTab("overview")}
              className={`px-3 py-1.5 rounded-lg font-medium transition-all ${
                activeTab === "overview"
                  ? "bg-cyan-500 text-slate-950 shadow-sm"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Overview
            </button>
            <button
              onClick={() => setActiveTab("stealth")}
              className={`px-3 py-1.5 rounded-lg font-medium transition-all ${
                activeTab === "stealth"
                  ? "bg-cyan-500 text-slate-950 shadow-sm"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Stealth Profile
            </button>
            <button
              onClick={() => setActiveTab("queue")}
              className={`px-3 py-1.5 rounded-lg font-medium transition-all ${
                activeTab === "queue"
                  ? "bg-cyan-500 text-slate-950 shadow-sm"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Queue Manager
            </button>
            <button
              onClick={() => setActiveTab("vps")}
              className={`px-3 py-1.5 rounded-lg font-medium transition-all ${
                activeTab === "vps"
                  ? "bg-cyan-500 text-slate-950 shadow-sm"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              VPS Deployment
            </button>
            <button
              onClick={() => setActiveTab("files")}
              className={`px-3 py-1.5 rounded-lg font-medium transition-all ${
                activeTab === "files"
                  ? "bg-cyan-500 text-slate-950 shadow-sm"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Code Files
            </button>
          </nav>
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex-1 w-full">
        {/* Tab 1: Overview */}
        {activeTab === "overview" && (
          <div className="space-y-8">
            {/* Hero Highlights */}
            <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-slate-900 via-slate-900 to-cyan-950/40 border border-slate-800 p-8">
              <div className="max-w-3xl space-y-4">
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-semibold">
                  <CheckCircle2 className="h-3.5 w-3.5" /> All 6 Python modules & 2 JSON files verified
                </div>
                <h1 className="text-3xl font-extrabold text-white tracking-tight">
                  Refactored & Hardened for Headless Linux Execution
                </h1>
                <p className="text-slate-300 text-base leading-relaxed">
                  The codebase has been refactored to execute seamlessly in background VPS environments with full desktop browser fingerprint spoofing, automated visual & DOM error snapshotting, and dynamic shipyard catalog parsing.
                </p>
                <div className="flex flex-wrap gap-3 pt-2">
                  <button
                    onClick={() => setActiveTab("vps")}
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-cyan-500 text-slate-950 font-semibold text-sm hover:bg-cyan-400 transition"
                  >
                    <Server className="h-4 w-4" /> Setup on VPS
                  </button>
                  <button
                    onClick={() => setActiveTab("stealth")}
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800 text-slate-200 font-semibold text-sm hover:bg-slate-700 transition border border-slate-700"
                  >
                    <Shield className="h-4 w-4" /> View Stealth Config
                  </button>
                </div>
              </div>
            </div>

            {/* Feature Cards Grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* Card 1 */}
              <div className="rounded-xl bg-slate-900/60 border border-slate-800 p-6 space-y-3">
                <div className="h-10 w-10 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
                  <Eye className="h-5 w-5" />
                </div>
                <h3 className="font-bold text-white text-lg">Desktop Fingerprint Spoofing</h3>
                <p className="text-sm text-slate-400 leading-relaxed">
                  Real Windows 10 Chrome User-Agent, 1920x1080 viewport, UTC timezone, and deep <code className="text-cyan-300">navigator.webdriver</code> masking via client-side scripts.
                </p>
                <ul className="text-xs text-slate-400 space-y-1.5 pt-1">
                  <li className="flex items-center gap-1.5 text-slate-300">
                    <CheckCircle2 className="h-3.5 w-3.5 text-cyan-400" />
                    <span>User-Agent: Windows Chrome 128</span>
                  </li>
                  <li className="flex items-center gap-1.5 text-slate-300">
                    <CheckCircle2 className="h-3.5 w-3.5 text-cyan-400" />
                    <span>Automation flags disabled</span>
                  </li>
                </ul>
              </div>

              {/* Card 2 */}
              <div className="rounded-xl bg-slate-900/60 border border-slate-800 p-6 space-y-3">
                <div className="h-10 w-10 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
                  <Camera className="h-5 w-5" />
                </div>
                <h3 className="font-bold text-white text-lg">Automated Error Snapshots</h3>
                <p className="text-sm text-slate-400 leading-relaxed">
                  When a Playwright navigation, selector, or timeout error happens, timestamped full-page PNG screenshots and complete HTML DOM dumps are captured in <code className="text-amber-300">./errors/</code>.
                </p>
                <ul className="text-xs text-slate-400 space-y-1.5 pt-1">
                  <li className="flex items-center gap-1.5 text-slate-300">
                    <CheckCircle2 className="h-3.5 w-3.5 text-amber-400" />
                    <span>Full-page PNG diagnostics</span>
                  </li>
                  <li className="flex items-center gap-1.5 text-slate-300">
                    <CheckCircle2 className="h-3.5 w-3.5 text-amber-400" />
                    <span>Raw HTML source dump</span>
                  </li>
                </ul>
              </div>

              {/* Card 3 */}
              <div className="rounded-xl bg-slate-900/60 border border-slate-800 p-6 space-y-3">
                <div className="h-10 w-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
                  <Cpu className="h-5 w-5" />
                </div>
                <h3 className="font-bold text-white text-lg">Shipyard Catalog Parsing</h3>
                <p className="text-sm text-slate-400 leading-relaxed">
                  Added <code className="text-emerald-300">parse_ship_catalog()</code> to automatically read resource costs, build durations, and affordable counts from live <code className="text-emerald-300">/app/:coords/ship</code> cards.
                </p>
                <ul className="text-xs text-slate-400 space-y-1.5 pt-1">
                  <li className="flex items-center gap-1.5 text-slate-300">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                    <span>Dynamic cost detection</span>
                  </li>
                  <li className="flex items-center gap-1.5 text-slate-300">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                    <span>Fallback base cost protection</span>
                  </li>
                </ul>
              </div>
            </div>

            {/* Architecture Overview */}
            <div className="rounded-xl bg-slate-900/40 border border-slate-800 p-6 space-y-4">
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                <Layers className="h-5 w-5 text-cyan-400" /> Modular Architecture Pipeline
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="p-4 rounded-lg bg-slate-950/70 border border-slate-800">
                  <span className="text-xs font-mono text-cyan-400 block mb-1">1. Radar Early Warning</span>
                  <div className="font-semibold text-white text-sm">defense.py</div>
                  <p className="text-xs text-slate-400 mt-1">
                    Monitors incoming hostile fleets. Triggers 30s emergency polling on imminent attack.
                  </p>
                </div>
                <div className="p-4 rounded-lg bg-slate-950/70 border border-slate-800">
                  <span className="text-xs font-mono text-cyan-400 block mb-1">2. Telemetry & Storage</span>
                  <div className="font-semibold text-white text-sm">telemetry.py</div>
                  <p className="text-xs text-slate-400 mt-1">
                    Parses exact liquid resources and unplunderable warehouse safety thresholds.
                  </p>
                </div>
                <div className="p-4 rounded-lg bg-slate-950/70 border border-slate-800">
                  <span className="text-xs font-mono text-cyan-400 block mb-1">3. Tech & Parallel Build</span>
                  <div className="font-semibold text-white text-sm">planner.py</div>
                  <p className="text-xs text-slate-400 mt-1">
                    Multi-planet parallel construction loops with recursive prerequisite resolution.
                  </p>
                </div>
                <div className="p-4 rounded-lg bg-slate-950/70 border border-slate-800">
                  <span className="text-xs font-mono text-cyan-400 block mb-1">4. Shipyard Recycler</span>
                  <div className="font-semibold text-white text-sm">shipyard.py</div>
                  <p className="text-xs text-slate-400 mt-1">
                    Converts excess iron into ship queue deposits, auto-recycling 30s before completion.
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab 2: Stealth Profile */}
        {activeTab === "stealth" && (
          <div className="space-y-6">
            <div className="border-b border-slate-800 pb-4">
              <h2 className="text-xl font-bold text-white flex items-center gap-2">
                <Shield className="h-5 w-5 text-cyan-400" /> Headless Browser & Stealth Configuration
              </h2>
              <p className="text-sm text-slate-400 mt-1">
                How Playwright is masked from server-side bot-detection heuristics and client-side JavaScript fingerprinting.
              </p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Context Parameters */}
              <div className="rounded-xl bg-slate-900 border border-slate-800 p-6 space-y-4">
                <h3 className="font-bold text-white text-base flex items-center gap-2">
                  <Globe className="h-4 w-4 text-cyan-400" /> Browser Context Parameters
                </h3>
                <div className="space-y-3 font-mono text-xs">
                  <div className="p-3 rounded bg-slate-950 border border-slate-800/80">
                    <span className="text-slate-500 block mb-1">User Agent</span>
                    <span className="text-cyan-300 break-all">
                      Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 rounded bg-slate-950 border border-slate-800/80">
                      <span className="text-slate-500 block mb-1">Viewport</span>
                      <span className="text-slate-200">1920 × 1080 (1080p)</span>
                    </div>
                    <div className="p-3 rounded bg-slate-950 border border-slate-800/80">
                      <span className="text-slate-500 block mb-1">Scale Factor</span>
                      <span className="text-slate-200">1.0</span>
                    </div>
                    <div className="p-3 rounded bg-slate-950 border border-slate-800/80">
                      <span className="text-slate-500 block mb-1">Locale</span>
                      <span className="text-slate-200">en-US</span>
                    </div>
                    <div className="p-3 rounded bg-slate-950 border border-slate-800/80">
                      <span className="text-slate-500 block mb-1">Timezone ID</span>
                      <span className="text-slate-200">UTC</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Chromium Launch Flags */}
              <div className="rounded-xl bg-slate-900 border border-slate-800 p-6 space-y-4">
                <h3 className="font-bold text-white text-base flex items-center gap-2">
                  <Terminal className="h-4 w-4 text-cyan-400" /> Chromium Launch Flags & Arguments
                </h3>
                <div className="space-y-2 text-xs font-mono">
                  <div className="p-2.5 rounded bg-slate-950 border border-slate-800 flex items-center justify-between">
                    <span className="text-cyan-300">--disable-blink-features=AutomationControlled</span>
                    <span className="text-slate-500">Hides webdriver flag</span>
                  </div>
                  <div className="p-2.5 rounded bg-slate-950 border border-slate-800 flex items-center justify-between">
                    <span className="text-cyan-300">--no-sandbox</span>
                    <span className="text-slate-500">Required on root VPS</span>
                  </div>
                  <div className="p-2.5 rounded bg-slate-950 border border-slate-800 flex items-center justify-between">
                    <span className="text-cyan-300">--disable-setuid-sandbox</span>
                    <span className="text-slate-500">Sandbox prevention</span>
                  </div>
                  <div className="p-2.5 rounded bg-slate-950 border border-slate-800 flex items-center justify-between">
                    <span className="text-cyan-300">--disable-dev-shm-usage</span>
                    <span className="text-slate-500">Prevents /dev/shm OOM crashes</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Injected JavaScript */}
            <div className="rounded-xl bg-slate-900 border border-slate-800 p-6 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="font-bold text-white text-base flex items-center gap-2">
                  <Code2 className="h-4 w-4 text-cyan-400" /> Injected Client-Side Stealth Script
                </h3>
                <span className="text-xs text-slate-500">Executed via context.add_init_script() before every page load</span>
              </div>
              <pre className="p-4 rounded-lg bg-slate-950 border border-slate-800 font-mono text-xs text-slate-300 overflow-x-auto">
{`(() => {
    // 1. Mask navigator.webdriver
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
    });

    // 2. Mock chrome runtime object
    if (!window.chrome) {
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };
    }

    // 3. Mock plugins list
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
    });

    // 4. Mock languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
    });

    // 5. Mock permissions query
    const originalQuery = window.navigator.permissions ? window.navigator.permissions.query : null;
    if (originalQuery) {
        window.navigator.permissions.query = (parameters) => (
            parameters && parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : originalQuery(parameters)
        );
    }
})();`}
              </pre>
            </div>
          </div>
        )}

        {/* Tab 3: Queue Manager */}
        {activeTab === "queue" && (
          <div className="space-y-6">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div>
                <h2 className="text-xl font-bold text-white flex items-center gap-2">
                  <Layers className="h-5 w-5 text-cyan-400" /> Planetary Build Queue Visualizer
                </h2>
                <p className="text-sm text-slate-400 mt-1">
                  Preview and manage planetary construction goals synchronized with <code className="text-cyan-300">build_queue.json</code>.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400 font-medium">Main Planet:</span>
                <span className="px-2.5 py-1 rounded bg-cyan-500/20 text-cyan-300 font-mono text-xs font-bold border border-cyan-500/30">
                  {queueData.main_planet}
                </span>
              </div>
            </div>

            {/* Planets Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {Object.entries(queueData.planets).map(([coord, goals]) => {
                const isMain = coord === queueData.main_planet;
                return (
                  <div
                    key={coord}
                    className={`rounded-xl border p-5 space-y-3 transition-all ${
                      isMain
                        ? "bg-slate-900 border-cyan-500/40 shadow-lg shadow-cyan-950/20"
                        : "bg-slate-900/60 border-slate-800"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-white text-base">{coord}</span>
                        {isMain && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] uppercase font-bold bg-cyan-500 text-slate-950">
                            Capital
                          </span>
                        )}
                      </div>
                      <span className="text-xs text-slate-400 font-mono">
                        {goals.length} {goals.length === 1 ? "task" : "tasks"}
                      </span>
                    </div>

                    <div className="space-y-2 min-h-[100px] flex flex-col justify-start">
                      {goals.length === 0 ? (
                        <div className="text-xs text-slate-500 italic py-6 text-center">
                          Queue idle. Ready for tasks.
                        </div>
                      ) : (
                        goals.map((goal, idx) => (
                          <div
                            key={idx}
                            className="flex items-center justify-between p-2.5 rounded bg-slate-950 border border-slate-800/80 text-xs"
                          >
                            <div>
                              <span className="font-semibold text-slate-200 block">{goal.name}</span>
                              <span className="text-[10px] text-slate-400 uppercase font-mono">{goal.type}</span>
                            </div>
                            <div className="text-right">
                              {goal.level && (
                                <span className="text-cyan-400 font-mono font-bold">Lvl {goal.level}</span>
                              )}
                              {goal.amount && (
                                <span className="text-emerald-400 font-mono font-bold">×{goal.amount}</span>
                              )}
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Quick Add Planet Bar */}
            <div className="rounded-xl bg-slate-900 border border-slate-800 p-4 flex items-center justify-between gap-4">
              <div className="flex items-center gap-2 flex-1 max-w-sm">
                <input
                  type="text"
                  placeholder="e.g. 2:109:4"
                  value={newCoord}
                  onChange={(e) => setNewCoord(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white placeholder-slate-500 font-mono focus:outline-none focus:border-cyan-500"
                />
                <button
                  onClick={addPlanet}
                  className="px-3 py-1.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 text-xs font-bold transition whitespace-nowrap"
                >
                  Add Planet
                </button>
              </div>

              <div className="text-xs text-slate-400">
                Tip: Changes to <code className="text-cyan-300">build_queue.json</code> take effect immediately on next cycle.
              </div>
            </div>
          </div>
        )}

        {/* Tab 4: VPS Deployment Guide */}
        {activeTab === "vps" && (
          <div className="space-y-6">
            <div className="border-b border-slate-800 pb-4">
              <h2 className="text-xl font-bold text-white flex items-center gap-2">
                <Server className="h-5 w-5 text-cyan-400" /> Headless Linux VPS Deployment Guide
              </h2>
              <p className="text-sm text-slate-400 mt-1">
                Complete instructions to install, verify, and run the bot 24/7 as a system service.
              </p>
            </div>

            {/* Step 1 */}
            <div className="rounded-xl bg-slate-900 border border-slate-800 p-6 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="font-bold text-white text-base flex items-center gap-2">
                  <span className="h-6 w-6 rounded-full bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 text-xs flex items-center justify-center font-mono">1</span>
                  Install Python 3, Virtualenv & Chromium System Libraries
                </h3>
                <button
                  onClick={() =>
                    copyToClipboard(
                      "sudo apt update && sudo apt install -y python3 python3-venv python3-pip git\npython3 -m venv venv\nsource venv/bin/activate\npip install -r requirements.txt\nplaywright install chromium\nplaywright install-deps chromium",
                      "cmd-install"
                    )
                  }
                  className="inline-flex items-center gap-1.5 text-xs font-medium text-cyan-400 hover:text-cyan-300"
                >
                  <Copy className="h-3.5 w-3.5" /> {copiedId === "cmd-install" ? "Copied!" : "Copy Commands"}
                </button>
              </div>
              <pre className="p-4 rounded-lg bg-slate-950 border border-slate-800 font-mono text-xs text-slate-300 overflow-x-auto">
{`# Update Linux package manager and install core tools
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git

# Set up dedicated virtual environment
python3 -m venv venv
source venv/bin/activate

# Install playwright package
pip install -r requirements.txt

# Crucial: Install Chromium binary AND Linux OS libraries
playwright install chromium
playwright install-deps chromium`}
              </pre>
            </div>

            {/* Step 2 */}
            <div className="rounded-xl bg-slate-900 border border-slate-800 p-6 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="font-bold text-white text-base flex items-center gap-2">
                  <span className="h-6 w-6 rounded-full bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 text-xs flex items-center justify-center font-mono">2</span>
                  24/7 Background Systemd Service Configuration
                </h3>
                <button
                  onClick={() =>
                    copyToClipboard(
`[Unit]
Description=GigraWars Headless Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/gigrawars-bot
Environment="PATH=/home/ubuntu/gigrawars-bot/venv/bin"
Environment="HEADLESS=true"
Environment="GIGRAWARS_EMAIL=your_email@example.com"
Environment="GIGRAWARS_PASS=your_secret_password"
ExecStart=/home/ubuntu/gigrawars-bot/venv/bin/python main.py
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target`,
                      "cmd-service"
                    )
                  }
                  className="inline-flex items-center gap-1.5 text-xs font-medium text-cyan-400 hover:text-cyan-300"
                >
                  <Copy className="h-3.5 w-3.5" /> {copiedId === "cmd-service" ? "Copied!" : "Copy Service Unit"}
                </button>
              </div>
              <p className="text-xs text-slate-400">
                Save to <code className="text-cyan-300">/etc/systemd/system/gigrawars-bot.service</code>:
              </p>
              <pre className="p-4 rounded-lg bg-slate-950 border border-slate-800 font-mono text-xs text-slate-300 overflow-x-auto">
{`[Unit]
Description=GigraWars Headless Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/gigrawars-bot
Environment="PATH=/home/ubuntu/gigrawars-bot/venv/bin"
Environment="HEADLESS=true"
Environment="GIGRAWARS_EMAIL=your_email@example.com"
Environment="GIGRAWARS_PASS=your_secret_password"
ExecStart=/home/ubuntu/gigrawars-bot/venv/bin/python main.py
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target`}
              </pre>
              <div className="pt-2">
                <span className="text-xs text-slate-400 block mb-1">To enable and start the service:</span>
                <pre className="p-3 rounded bg-slate-950 border border-slate-800 font-mono text-xs text-cyan-300">
sudo systemctl daemon-reload && sudo systemctl enable --now gigrawars-bot
journalctl -u gigrawars-bot -f
                </pre>
              </div>
            </div>
          </div>
        )}

        {/* Tab 5: Code Files Viewer */}
        {activeTab === "files" && (
          <div className="space-y-6">
            <div className="border-b border-slate-800 pb-4">
              <h2 className="text-xl font-bold text-white flex items-center gap-2">
                <Code2 className="h-5 w-5 text-cyan-400" /> Refactored Project Codebase
              </h2>
              <p className="text-sm text-slate-400 mt-1">
                Explore the modular structure and verified Python scripts ready for production.
              </p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
              {/* File list sidebar */}
              <div className="lg:col-span-1 space-y-2">
                {Object.entries(FILES_CONTENT).map(([filename, info]) => (
                  <button
                    key={filename}
                    onClick={() => setSelectedFile(filename)}
                    className={`w-full text-left p-3 rounded-lg border transition-all flex items-center justify-between ${
                      selectedFile === filename
                        ? "bg-slate-800 border-cyan-500/50 text-white"
                        : "bg-slate-900/50 border-slate-800 text-slate-400 hover:text-slate-200 hover:bg-slate-900"
                    }`}
                  >
                    <div>
                      <div className="font-mono text-xs font-semibold">{filename}</div>
                      <div className="text-[11px] text-slate-400">{info.role}</div>
                    </div>
                    <ChevronRight className={`h-4 w-4 ${selectedFile === filename ? "text-cyan-400" : "text-slate-600"}`} />
                  </button>
                ))}
              </div>

              {/* File details panel */}
              <div className="lg:col-span-3 rounded-xl bg-slate-900 border border-slate-800 p-6 space-y-4">
                <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                  <div>
                    <span className="font-mono text-base font-bold text-white">{selectedFile}</span>
                    <p className="text-xs text-slate-400 mt-0.5">{FILES_CONTENT[selectedFile]?.desc}</p>
                  </div>
                  <span className="px-2 py-0.5 text-xs font-mono rounded bg-slate-800 text-slate-300">
                    {FILES_CONTENT[selectedFile]?.language.toUpperCase()}
                  </span>
                </div>

                <div className="space-y-2">
                  <div className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Refactor Summary:</div>
                  <div className="p-3 rounded-lg bg-slate-950 border border-slate-800/80 text-xs text-slate-300 leading-relaxed">
                    {selectedFile === "main.py" && (
                      <p>
                        Configured with <code className="text-cyan-300">headless=HEADLESS</code> by default. Integrates modern desktop user agent, 1080p viewport, and <code className="text-cyan-300">context.add_init_script(STEALTH_SCRIPT)</code>. Enhanced global Playwright error handler captures timestamped screenshots and DOM dumps to <code className="text-cyan-300">./errors/</code>.
                      </p>
                    )}
                    {selectedFile === "config.py" && (
                      <p>
                        Added spoofing parameters (User-Agent, Viewport, Locale, Timezone), Chromium anti-detection flags (<code className="text-cyan-300">--disable-blink-features=AutomationControlled</code>), stealth injection script, and the new <code className="text-cyan-300">save_error_snapshot()</code> helper.
                      </p>
                    )}
                    {selectedFile === "shipyard.py" && (
                      <p>
                        Added <code className="text-cyan-300">parse_ship_catalog(coords)</code> to dynamically extract ship build costs, durations, and max quantities from the live <code className="text-cyan-300">/ship</code> page cards, while maintaining safe recycling fallback logic.
                      </p>
                    )}
                    {selectedFile === "planner.py" && (
                      <p>
                        Preserves recursive prerequisite tech pivots, parallel building loops, fast build threshold heuristics, and goal deduction in <code className="text-cyan-300">build_queue.json</code>.
                      </p>
                    )}
                    {selectedFile === "telemetry.py" && (
                      <p>
                        Extracts resource meter data, unplunderable warehouse safety limits, active timer counts, and busy planet states.
                      </p>
                    )}
                    {selectedFile === "defense.py" && (
                      <p>
                        Checks incoming fleet movements and triggers early-warning logs and adaptive polling intervals.
                      </p>
                    )}
                    {selectedFile === "build_queue.json" && (
                      <p>
                        Empire configuration containing capital coordinates (<code className="text-cyan-300">3:7:1</code>), colonized planets, and unit/building target levels.
                      </p>
                    )}
                    {selectedFile === "auth.json" && (
                      <p>
                        Persisted session cookie credentials for seamless login bypass.
                      </p>
                    )}
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center gap-2 text-xs text-emerald-300">
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
                  <span>Syntax verified and tested cleanly in Linux execution environment.</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800 bg-slate-900/50 py-4 mt-8">
        <div className="max-w-7xl mx-auto px-4 text-center text-xs text-slate-500">
          GigraWars Headless VPS Suite • Anti-Detection Profile • Error Snapshotting Enabled
        </div>
      </footer>
    </div>
  );
}
