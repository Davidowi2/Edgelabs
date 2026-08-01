# VPS Setup Checklist — EdgeLab (Phase 9a)

A new operator should be able to deploy EdgeLab end-to-end by reading this
runbook. Estimated total setup time: **2–3 hours** (plus broker account setup).

Each item: **what to do / why it matters / how to verify**.

---

## 1. Windows OS Configuration

- [ ] **Auto-login (unattended):** Configure Winlogon auto-login for the trading user so the VPS resumes the session after a reboot. *Why:* power loss or patched reboots must not leave the terminal logged out. *Verify:* reboot the box and confirm the desktop auto-logs in and the terminal starts.

- [ ] **Disable Windows Update forced reboot:** Set `NoAutoRebootWithLoggedOnUsers=1` so updates install but never force-restart the trading session. *Why:* a forced reboot mid-trade can orphan positions and gap the account. *Verify:* `gpresult /r` shows the AU policy; confirm no pending forced restart in Windows Update.

- [ ] **Set power plan to High Performance:** `powercfg /setactive` the High Performance GUID. *Why:* balanced/saver plans throttle CPU and stall the terminal or Python EA under load. *Verify:* `powercfg /getactivescheme` returns the High Performance GUID.

- [ ] **Add antivirus (Defender) exclusion:** Exclude the MT5 data directory from real-time scanning. *Why:* AV scanning of tick/history files causes latency spikes and missed fills. *Verify:* `Get-MpPreference | Select -ExpandProperty ExclusionPath` lists the MT5 tree.

- [ ] **Disable visual effects / animations:** Set `VisualFXSetting=2` (performance). *Why:* frees CPU cycles for trading. *Verify:* Advanced System Settings → Performance → "Adjust for best performance" is selected.

- [ ] **Set timezone to broker time (UTC+3):** Configure the box clock to match the broker, and pass the same offset to `BrokerTime`. *Why:* the timezone-trap hotfix (Phase 1.5) rejects impossible offsets, but a wrong-yet-valid offset still corrupts sessions. *Verify:* `BrokerTime(offset="+3")` initializes with no warning; clock matches broker.

- [ ] **Run as non-admin trading user for daily use:** Use the auto-login account for the terminal; keep admin separate. *Why:* reduces blast radius of a compromised EA. *Verify:* terminal runs under the trading user, not Administrator.

---

## 2. MT5 Configuration

- [ ] **Create portable mode:** drop a `portable` file in each MT5 instance dir so all data lives beside the binary. *Why:* portable mode keeps histories, logs and config self-contained and easy to back up. *Verify:* a zero-byte `portable` file exists in each instance folder.

- [ ] **Create multi-instance directory structure:** `MT5_Instance1/`, `MT5_Instance2/` each with `MQL5/Experts/`, `MQL5/Presets/`, `MQL5/Files/`. *Why:* separate instances avoid shared-terminal contention and let you run redundant terminals. *Verify:* `install_mt5.sh` created both instances with the MQL5 sub-tree.

- [ ] **Fill MT5 account config:** edit `accounts.xml` / `terminal64.ini` with the real server, login and password. *Why:* placeholders will not connect. *Verify:* terminal logs in and shows account equity.

- [ ] **Deploy the Edgelab EA + presets:** copy the compiled EA into `MQL5/Experts/` and the `.set` presets into `MQL5/Presets/`. *Why:* the EA is what calls the Python gateway. *Verify:* EA appears in Navigator and loads on the chart.

- [ ] **Enable Algo/AutoTrading:** allow automated trading in terminal options. *Why:* the EA cannot trade if AutoTrading is off. *Verify:* terminal shows "Algo Trading" enabled (green).

- [ ] **Set correct broker timezone in terminal:** match `BrokerTime` offset. *Why:* session/time math routes through `BrokerTime`; mismatch corrupts timing. *Verify:* terminal market watch times match broker-local times.

---

## 3. Network

- [ ] **Allowlist broker + gateway endpoints:** open outbound to the broker's trade server and the Python gateway port. *Why:* a blocked port = no fills. *Verify:* `Test-NetConnection` / `curl` to the endpoint succeeds.

- [ ] **Disable sleep on network idle:** keep the connection alive; consider a keep-alive ping. *Why:* idle disconnects drop the session silently. *Verify:* terminal stays connected through a 10-minute idle.

- [ ] **Static IP or DDNS:** ensure the VPS keeps a reachable address for monitoring. *Why:* monitoring alerts need a stable target. *Verify:* the monitoring box can reach the VPS.

---

## 4. Monitoring

- [ ] **Install the watchdog:** schedule `watchdog.sh` (Linux) or `watchdog.ps1` (Windows) every 5 minutes via cron / Task Scheduler. *Why:* auto-restarts a dead terminal instead of waiting for a human. *Verify:* kill `terminal64.exe` manually and confirm it restarts within 5 min.

- [ ] **Install the health check:** schedule `health_check.sh` and wire its exit code (0 healthy / 1 degraded / 2 critical) to your monitoring system. *Why:* surfaces DEGRADED/CRITICAL before the account is harmed. *Verify:* `health_check.sh; echo $?` returns 0 when healthy.

- [ ] **Wire alerts:** set `AlertOnRestart` so the operator gets a ping when MT5 dies and on restart. *Why:* silent deaths are the worst kind. *Verify:* a forced kill produces an alert line in the log.

- [ ] **Centralize logs:** ship `ea.log`, `watchdog.log` and Python logs to one place. *Why:* post-incident forensics need the full trail. *Verify:* logs are queryable from the monitoring console.

---

## 5. Backup

- [ ] **Nightly backup:** schedule `nightly_backup.sh` (rsync) or the robocopy equivalent nightly. *Why:* a corrupted MT5 state or lost presets is recoverable. *Verify:* a dated backup dir appears under `backups/`.

- [ ] **7-day rolling retention:** keep 7 days of backups, prune older. *Why:* bounds disk usage while covering a full week of incidents. *Verify:* only the last 7 dated dirs remain.

- [ ] **Back up the right dirs:** `MQL5/Experts/`, `MQL5/Presets/`, `MQL5/Files/`, `config/`, `profiles/`, `Bases/`. *Why:* these hold the EA, settings, ticks and history. *Verify:* restored dir contains the EA + presets.

- [ ] **Test a restore:** once, restore a backup to a scratch instance and confirm the EA loads. *Why:* an untested backup is a hope, not a backup. *Verify:* scratch instance runs the EA from the restored files.

---

## 6. Security

- [ ] **Store credentials securely:** keep `accounts.xml` passwords out of version control; prefer vault or restricted ACLs. *Why:* leaked creds = direct account theft. *Verify:* the file is not committed; ACL limits read to the trading user.

- [ ] **Least privilege:** trading user is not admin; admin used only for setup. *Why:* limits damage from a compromised EA. *Verify:* terminal runs as the non-admin user.

- [ ] **Firewall:** only required ports open; RDP restricted (IP allowlist / non-default port + strong creds). *Why:* RDP is a top ransomware vector. *Verify:* `nmap` from outside shows only intended ports.

- [ ] **Patch cadence:** schedule updates in a maintenance window that does not overlap trading hours. *Why:* updates are needed but must not force a mid-session reboot. *Verify:* update history shows installs outside trading hours.

- [ ] **Audit the timezone config:** re-check `BrokerTime` offset after any timezone/DST change. *Why:* the Phase 1.5 hotfix rejects impossible offsets, but a valid-but-wrong offset still corrupts 3 months of data. *Verify:* `BrokerTime(offset="+3")` logs no warning; periodic review in the runbook.

---

## 7. Go-Live Verification

- [ ] **Run the full pipeline integration test:** `pytest tests/test_full_pipeline_integration.py` passes (proves Phase 7→3→2→4→8 compose safely). *Why:* this is the test that catches a broken composition. *Verify:* 12 tests green.

- [ ] **Run the startup check:** `StartupValidator.run_all_checks()` passes including `execution_config`. *Why:* fails loud on a missing/misconfigured execution layer. *Verify:* `passed=True`.

- [ ] **Paper/demo first:** trade on demo for the full forward-test window before micro-live. *Why:* Phase 10 forward test de-risks the real account. *Verify:* demo trades execute end-to-end via the gateway.
