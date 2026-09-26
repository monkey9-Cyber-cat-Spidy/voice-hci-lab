# docs: Interactive Demonstrations and Video Production Protocols

## Abstract

Technical communication is an essential component of frontier HCI engineering. This directory contains production protocols, demonstration walkthrough scripts, and presentation specifications for showcasing speculative computer use and in-place streaming disfluency correction.

---

## 1. Documentation Artifacts

- **`DEMO_SCRIPT.md`**: A 60-second screen recording protocol with detailed shot lists, verbal scripts, and visual choreography designed for public presentations on X, LinkedIn, and research forums.

---

## 2. Interactive Live Walkthrough Protocol

To demonstrate the systems live on a desktop workstation:

### Scenario A: In-Place Thought-Stream Correction (Notepad / Slack)
1. Position a terminal window and an empty text editor (Notepad or Slack) side-by-side.
2. In the terminal, execute:
   ```bash
   python -m thought_stream.cli demo --live --delay 0.15 -v
   ```
3. Within the 3-second countdown window, click into the empty text editor to focus the active caret.
4. Watch the system type the initial phrase (*"the deployment is ready"*), detect the spoken pivot (*"actually wait make that"*), dispatch atomic hardware backspaces, and type the updated intention (*"delayed until 4 PM"*) seamlessly in-place.

### Scenario B: Speculative Voice-to-Action Execution
1. Open PowerShell and execute:
   ```bash
   python -m voice_action.cli say --real "open notepad"
   ```
2. Observe the latency telemetry readout:
   ```text
   open notepad   speculation=on 
     first hypothesis @      1 ms
     prewarm          @      5 ms
     first UI change  @     46 ms   <- TTFA (real desktop app launched)
     commit done      @     46 ms
     actions: ['open notepad']  ok=True
   ```

### Scenario C: Interactive Benchmark Exploration
1. Launch the local web server:
   ```bash
   python -m voicehci_bench.cli serve --port 8765
   ```
2. Open `http://localhost:8765` in a browser.
3. Explore the Pareto efficiency frontier, inspect per-category error heatmaps, and review individual test records in the interactive record explorer.
