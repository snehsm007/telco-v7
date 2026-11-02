# 10 Automated audio evals (text first, audio simulations & naturalness last)

Audio evaluations send real synthesized speech through the full voice pipeline (Speech-to-Text (**STT**), Large Language Model (**LLM**), Text-to-Speech (**TTS**)) without a human placing a phone call. Because audio evaluations are slower, cost more, and use a separate, smaller concurrency quota, **always run them only after the text evaluation gate is green**.

---

## Critical Platform Finding (`DEF-A01`): Why Natural-Voice Audio Simulations Beat Scripted Audio Goldens

In production GECX testing (`DD-30`, `DEF-A01`), running scripted golden evaluations with `--modality audio` scored **26/51 (51%)** while the exact same agent version scored **41/51 (80%)** in text mode and **>85%** in audio simulations:
- **Root Cause (`DEF-A01` — Platform Audio Runner Drops 1-Word Scripted Openers):** When `cxas run --modality audio` synthesizes a scripted golden turn containing a short 1-word opener (`"Hello"`, `"Hi"`, `"Bonjour"`, `"Hola"`), the platform's voice turn-taking / Voice Activity Detection (**VAD**) frequently clips or drops the 1-word utterance before STT transcribes it. The agent receives an empty or silent turn, triggers silence-recovery instead of the scripted Turn 1 flow, and every subsequent scripted turn in the golden fails alignment.
- **Additionally**, platform audio goldens silently skip `expect_tools` assertions unless graded externally by `suite/grader.py`.

### The Recommended Audio Benchmark Strategy (`DD-29`, `DD-30`)
Use **Natural-Voice Audio Simulations (`SimulationEvals` with `modality="audio"`)** as your primary voice benchmark, where Gemini plays the caller and speaks full natural sentences:
1. **P0 Audio Simulations (Task Outcome + Expectations):** Run your Priority 0 (**P0**) simulation suite in audio mode (`scripts/run_evals.py --modality audio`) and pair it with a 1× text-mode run on the exact same app version so you can immediately separate voice/STT artifacts from logic bugs.
2. **SCRAPI Speech Naturalness Grader (`DD-29`):** Grade the recorded agent audio in Google Cloud Storage (**GCS**) across per-turn speech qualities, overall naturalness score, and descriptive label. Target: **zero languages with a median turn label of `"Bot-like"`**, and fix any voice-formatting findings (spoken markdown/markup, account/phone digits read as giant integers instead of grouped digits, dropped emotive tags, or turns exceeding 4 seconds of perceived latency).
3. **Noise-Variant Audio Simulations (3–5 P0 scenarios):** Run SCRAPI's local bidirectional streaming simulator with Cloud Text-to-Speech injecting background pink noise and burst clicks (`voice_config` noise options) to verify that `noiseSuppressionLevel: "HIGH"` prevents false barge-ins.
4. **Human Ear Check:** Have a human listen to at least 3–5 saved `.wav` recordings from the GCS audio bucket (`gs://<agent>-audio/eval-audio/$session`) to verify pacing, pronunciation, and natural handoffs.

---

## Pre-Audio Checklist: `make voice-audit` (`cxas-composite-voice-agent-optimizer`)

Before running a single cloud audio evaluation, run SCRAPI's built-in voice readiness audit offline:
```bash
make voice-audit
# 1. Checks cxas_app/app.json: gemini-composite-v1, bargeInAwareness=True, noiseSuppressionLevel=HIGH
# 2. When the cxas-composite-voice-agent-optimizer skill is installed, runs its audit:
#    python ~/.gemini/config/skills/cxas-composite-voice-agent-optimizer/scripts/audit_agent.py --workspace cxas_app --report --json
```
Verify all four **Gemini Composite V1 (`gemini-composite-v1`)** requirements pass with 0 P0/P1 errors:
1. **Rule A007 (Director's Note):** Every declared language has a natural voice-style Director's Note configured.
2. **Rule A008 (Accent Wording):** Accent labels match SCRAPI's expected canonical strings (e.g., `"French Canadian"` for `fr-CA`, `"Spanish accent"` for `es-US`) so the linter emits zero warnings.
3. **Rule A009 (Language Coverage):** Every supported language (`en-US`, `fr-CA`, `es-US`) has complete voice and speech settings in `app.json`.
4. **Rule A010 (Temperature & Noise Suppression):** Temperature is `1.0` (`make kickstart` writes it into `cxas_app/app.json` from `TEMPERATURE ?= 1.0`), and `noiseSuppressionLevel: "HIGH"` is set on both the default channel profile and phone deployments. Temperature 1.0 is final: it is the owner's decision, and a text-simulation test in `telco-rebuild` found no measurable difference between 0.2 and 1.0 (41/50 strict at 0.2 vs 40/50 at 1.0, with the failing tests rotating between runs).

---

## Configuring Audio Recording in `app.json` (and Preserving It Across Pushes)

An overwriting `cxas push` resets app-level audio recording settings unless they are declared in `cxas_app/app.json` and re-applied by your push script:
- Set `loggingSettings.evaluationAudioRecordingConfig`:
  - `gcsBucket`: `"gs://<your-audio-bucket>"` (must start with `gs://` and have **no trailing slash**).
  - `gcsPathPrefix`: `"eval-audio/$session"` (must contain the literal token `$session`).
- If running the noise variant via SCRAPI local streaming, ensure the Cloud Text-to-Speech API (`texttospeech.googleapis.com`) is enabled in your Google Cloud Platform (**GCP**) project (`DD-29`).

---

## Voice Gotchas to Check with `suite/grader.py`
- Run `suite/grader.py` on every audio transcript: leaked code read aloud, markdown (`**`, `*`, `#`), URLs, emoji, overly long replies (`reply_chars_max`), dead air before transfers, or wrong language.
- Voice conversations take more turns than text chats (due to confirmations, barge-ins, and silence recovery). Set `max_turns` 4–6 turns higher than text simulations.
- Voice session concurrency quota is small: run audio evaluations at `--parallel 1` or `2` to avoid HTTP 429 quota drops.
- Group spoken digits (`"2 0 2, 5 5 5, 0 1 4 3"`, never `"two billion..."`) and ensure `speech_hygiene` (backed by `lib/speech.py`) strips any formatting symbols before TTS synthesis, while tools normalize incoming digits via `normalize_code(value)` (which strips trailing `.0` float strings before extracting digits; `docs/DESIGN_RULES.md` rule 22).
