# NeuroLearn — three-minute pitch

Eight main slides plus two hidden technical backup slides. Main timings total 180 seconds. Suggested division: Speaker 1 takes slides 1–3; Speaker 2 takes slides 4–5; Speaker 3 takes slides 6–8. Slides 9–10 are hidden in PowerPoint and are for Q&A only; the PDF includes them. Any group size can use the same timing.

## The promise

**0:00–0:18 · 18 seconds | Speaker 1**

Have you ever lost focus during a lecture and realized the next explanation no longer makes sense? NeuroLearn helps students recover that missing piece, connecting attention signals with the lecture moment so they can return to learning with context.

## The student problem

**0:18–0:36 · 18 seconds | Speaker 1**

A brief lapse creates more than lost time. Students lose the thread, search backward, and may still struggle with the explanation. Our opportunity is to make recovery easier before one missed step becomes a bigger learning gap.

## The product

**0:36–1:01 · 25 seconds | Speaker 1**

Our prototype senses a possible lapse, captures the corresponding video timestamps, and offers a choice: replay the segment, ask for an explanation, or continue. The AI uses captions from that interval to summarize the material and offer a review question. The student stays in control.

## Our technical approach

**1:01–1:31 · 30 seconds | Speaker 2**

Technically, the board streams EEG into Python. We filter a five-second window into alpha and beta bands, estimate their power, and compare the ratio with a personal calibration baseline. Sustained threshold crossings update the desktop through Flask. The browser records the lecture interval, and local Ollama explains its captions. The attention detector is rule-based; the language model explains the content.

## Why alpha / beta?

**1:31–1:56 · 25 seconds | Speaker 2**

Why alpha over beta? Related research has studied beta over alpha as an engagement feature. We use the inverse as an interpretable candidate lapse signal. It is inexpensive to compute, needs no labeled training set, and can be compared with a personal baseline. It is a prototype heuristic that still needs validation.

## The student value

**1:56–2:16 · 20 seconds | Speaker 3**

The benefit is targeted review: revisit the relevant moment and get help understanding it. This example card illustrates that experience. Our prototype supports interval capture, replay, explanations, and saved history. Local AI and a clear-history button give students control.

## The business opportunity

**2:16–2:40 · 24 seconds | Speaker 3**

We would start with college STEM courses and learning-support teams. A small pool of loaner headsets lowers the adoption barrier. After demonstrating value in a pilot, we would test campus software licensing. The reason to pay is a better study experience, backed by evidence.

## The ask

**2:40–3:00 · 20 seconds | Speaker 3**

Our ask is one course partner and twenty volunteers for a two-week pilot. We would compare comprehension, recovery time, and repeat use against ordinary video review. Help us turn a working prototype into a better study experience. NeuroLearn: recover the moment, keep the momentum.

## Backup: signal processing and state logic

**Q&A only · hidden in slideshow | Any speaker**

The current code processes buffer[0], the first incoming channel, in a five-second sliding window. It removes the mean, uses butter(4) bandpass coefficients and filtfilt for alpha 8–13 Hz and beta 13–30 Hz, and estimates power using mean squared filtered amplitude. This is not an FFT-peak ratio; FFT peaks are displayed separately. Calibration averages ratios for ten seconds after a three-second countdown. At or above 1.8 times baseline the app publishes pending; after five continuous seconds it publishes unfocused. The desktop starts timing at pending, not after the alert. The 10-second ratio history is a display history, not the EEG power-estimation window. These numbers describe the current local test.py snapshot and are adjustable engineering choices. Calibration is available but is not enforced as a prerequisite by the app.

## Backup: scientific rationale and validation

**Q&A only · hidden in slideshow | Any speaker**

Research does not establish alpha as simply distraction or beta as simply focus. Our direction is a working hypothesis. Coelli et al. studied beta/alpha in nine adults performing a continuous-performance task and found montage-dependent relations with reaction time: https://pubmed.ncbi.nlm.nih.gov/26736558/ . Ahmed et al. investigated beta/(theta+alpha), beta/alpha, and inverse alpha in a cognitive-game task: https://pmc.ncbi.nlm.nih.gov/articles/PMC11991241/ . Their beta/alpha index alone did not significantly distinguish game difficulty levels; combined-feature classifiers performed better. Neither paper validates NeuroLearn's first-channel implementation, 1.8 multiplier, five-second persistence rule, or student learning outcomes. A ratio can cancel a common multiplicative amplitude scale in an idealized signal, but does not remove motion, eye or muscle artifacts, or electrode-placement effects. The current code does not implement explicit artifact rejection. Validate signal quality and compare alternative features using independent attention labels before claiming accuracy.

## Rehearsal tips

- Aim to finish the spoken content by 2:55; use the remaining seconds for handoffs and pauses. Shorten a sentence if rehearsal runs long.
- Use Presenter View: this script is also embedded in the PowerPoint speaker notes.
- Skip a live hardware demo in a strict three-minute slot. Offer it after the pitch.
- The recovery card is illustrative. Do not present it as a captured user result.
- The pilot size and campus licensing are proposals; there are no claims of existing customers, revenue, or proven learning gains.

## Likely questions

**Does it actually improve grades?**
We have a working recovery prototype, not evidence of improved grades. The pilot will measure comprehension and recovery time before making learning-outcome claims.

**Why EEG instead of a rewind button?**
The hypothesis is that attention signals can help identify moments worth revisiting without requiring the student to remember exactly when the gap occurred. EEG is an estimate, and users remain in control. The pilot should compare against ordinary video review.

**Will students wear headsets?**
That is an adoption question to test. Start with voluntary sessions and loaner devices rather than requiring every student to buy hardware.

**Why would a campus pay?**
Only if pilots show useful study outcomes and repeat usage at a workable cost. Campus licensing is a proposed model, not a signed customer commitment.

**What about privacy?**
The current default uses local Ollama and local recovery storage. Raw EEG is not sent to the language model. YouTube caption retrieval still needs internet access. There is a clear-history control; that removes recovery history, not separate EEG recordings.

**Can it explain every video?**
It currently relies on accessible captions in the configured language. It does not interpret diagrams or independently transcribe audio, and model answers can be wrong.
