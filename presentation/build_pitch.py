"""Build a timed pitch with technical approach and hidden Q&A slides."""
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent
prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333333), Inches(7.5)
prs.core_properties.title = "NeuroLearn | Recover the moment. Keep the momentum."
prs.core_properties.subject = "Three-minute student learning and business pitch"
prs.core_properties.author = "NeuroLearn Team"
BG, PANEL, WHITE, MUTED, MINT, AMBER = "101E2B", "1B2C3B", "F5F7FA", "B5C5D3", "7DE2C3", "FFC572"
slides, previews = [], []
SCALE = 120


def box(x, y, w, h, color=PANEL, radius=False):
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
                               Inches(x), Inches(y), Inches(w), Inches(h))
    sh.fill.solid()
    sh.fill.fore_color.rgb = RGBColor.from_string(color)
    sh.line.fill.background()
    draw.rectangle((int(x*SCALE), int(y*SCALE), int((x+w)*SCALE), int((y+h)*SCALE)), fill="#"+color)
    return sh


def text(x, y, w, h, value, size=22, color=WHITE, bold=False):
    sh = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = sh.text_frame
    tf.clear()
    tf.word_wrap = False
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, line in enumerate(value.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.font.name = "Arial"
        p.font.size = Pt(size)
        p.font.bold = bold
        p.font.color.rgb = RGBColor.from_string(color)
        p.space_before = Pt(0)
        p.space_after = Pt(0)
        p.line_spacing = 1.15
    font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf", round(size*SCALE/72))
    for i, line in enumerate(value.split("\n")):
        if draw.textlength(line, font=font) > w*SCALE + 2:
            raise ValueError(f"Text too wide: {line}")
        draw.text((x*SCALE, y*SCALE+i*size*SCALE/72*1.15), line, font=font, fill="#"+color)
    return sh


def start(number, section):
    global slide, canvas, draw
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = RGBColor.from_string(BG)
    canvas = Image.new("RGB", (1600, 900), "#"+BG)
    draw = ImageDraw.Draw(canvas)
    text(.65, .35, 4, .3, "NEUROLEARN", 12, MINT, True)
    text(8.7, .35, 4, .3, section.upper(), 11, MUTED)
    box(.65, 7.03, 12, .012, "344656")
    text(.65, 7.15, 10, .22, "Recover the moment. Keep the momentum.", 10, MUTED)
    text(12.05, 7.12, .6, .25, f"{number:02}", 12, MINT, True)


def finish(title, timing, speaker, script):
    slide.notes_slide.notes_text_frame.text = f"{title}\n{timing} | {speaker}\n\n{script}"
    previews.append(canvas)
    slides.append((title, timing, speaker, script))
    canvas.save(OUT / f"slide_{len(slides):02}.png")


start(1, "The promise")
text(.65, 1.2, 11.9, 1.9, "The lecture moves on.\nYour understanding should too.", 40, WHITE, True)
text(.68, 3.45, 10.8, .9, "An EEG-assisted learning companion that helps students\nrevisit and understand the moments they may have missed.", 23, MUTED)
box(.68, 5.25, 7.4, .78, MINT)
text(.95, 5.43, 7, .4, "Catch the gap. Get back to learning.", 24, BG, True)
text(9.05, 5.3, 3.6, .8, "YouTube lectures\n+ local AI recovery", 19, MINT)
finish("The promise", "0:00–0:20 · 20 seconds", "Speaker 1",
       "Have you ever watched a lecture, lost focus for a moment, and realized the next explanation no longer makes sense? NeuroLearn helps students recover that missing piece. We connect attention signals with the exact lecture moment, so students can get back to learning with context.")

start(2, "The student problem")
text(.65, 1.05, 12, 1.4, "A small lapse can create\na bigger learning gap.", 38, WHITE, True)
for x, number, title, body in [
    (.7, "01", "Lose the thread", "One missed step makes\nthe next idea harder to follow."),
    (4.95, "02", "Hunt for the moment", "Scrubbing backward means\nguessing what was missed."),
    (9.05, "03", "Replay without clarity", "Hearing it again may still\nleave the question unanswered.")]:
    text(x, 3.05, 1, .6, number, 32, AMBER, True)
    box(x, 3.85, 3.5, .025, "405365")
    text(x, 4.15, 3.7, .5, title, 21, WHITE, True)
    text(x, 4.95, 3.65, 1, body, 18, MUTED)
text(.7, 6.35, 12, .4, "The opportunity: turn a moment of confusion into a moment of recovery.", 21, MINT)
finish("The student problem", "0:20–0:45 · 25 seconds", "Speaker 1",
       "The problem is not simply distraction. It is what happens afterward. Students lose the thread, search backward through the video, and may still struggle with the explanation. In a technical lecture, the next concept often depends on the previous one. We want to make recovery easier, so a brief lapse does not have to derail the rest of a study session.")

start(3, "The product")
text(.65, 1.05, 12, 1.3, "From possible distraction\nto a useful next step.", 38, WHITE, True)
for x, step, title, body in [
    (.7, "SENSE", "Notice the moment", "EEG signals indicate\na possible attention lapse."),
    (4.95, "CAPTURE", "Save the context", "The extension records\nthe lecture timestamps."),
    (9.05, "RECOVER", "Choose your help", "Replay the segment or\nask AI to explain it.")]:
    box(x, 3.0, 3.55, 2.8)
    text(x+.2, 3.23, 3.1, .35, step, 12, MINT, True)
    text(x+.2, 3.95, 3.2, .5, title, 20, WHITE, True)
    text(x+.2, 4.7, 3.2, .9, body, 17, MUTED)
text(.7, 6.25, 12, .5, "Student stays in control: replay, explain, or continue.", 24, MINT, True)
finish("The product", "0:45–1:20 · 35 seconds", "Speaker 2",
       "NeuroLearn follows three steps. First, EEG signals indicate a possible attention lapse. Second, our browser extension saves the corresponding video timestamps. Third, when focus returns, the student chooses what helps: replay the segment more slowly, ask for an explanation, or continue. The AI uses captions from that interval to summarize the material, highlight key concepts, and offer a review question. The student stays in control.")

start(4, "Our technical approach")
text(.65, 1.05, 12, 1.2, "Turn a brain signal into\na useful learning action.", 36, WHITE, True)
for x, title, body in [
    (.7, "01 / ACQUIRE", "NeuroPawn board\nEEG via LSL"),
    (3.85, "02 / FILTER", "Alpha: 8–13 Hz\nBeta: 13–30 Hz"),
    (7.0, "03 / COMPARE", "Band-power ratio\nvs personal baseline"),
    (10.15, "04 / RESPOND", "Save video interval\nReplay or explain")]:
    box(x, 2.8, 2.5, 1.8)
    text(x+.12, 3.04, 2.3, .3, title, 12, MINT, True)
    text(x+.12, 3.65, 2.3, .75, body, 15, WHITE)
box(.7, 5.05, 11.95, 1.15, "243B49")
text(.95, 5.25, 11.4, .4, "RECOVERY: video timestamps → overlapping captions → local Ollama", 21, MINT, True)
text(.95, 5.77, 11.3, .3, "The language model explains the lecture; it does not classify the EEG.", 16, MUTED)
text(.7, 6.55, 12, .3, "Implemented pipeline. Focus classification is a rule-based prototype, not a trained neural network.", 12, MUTED)
finish("Our technical approach", "1:01–1:31 · 30 seconds", "Speaker 2", "")

start(5, "Why alpha / beta?")
text(.65, 1.05, 12, 1, "A simple signal we can explain\nand calibrate for each student.", 35, WHITE, True)
box(.7, 2.8, 5.6, 2.95)
text(.95, 3.05, 5.1, .4, "OUR FEATURE", 12, MINT, True)
text(.95, 3.75, 5.1, .6, "R = alpha power / beta power", 23, WHITE, True)
text(.95, 4.7, 5.05, .8, "Higher relative alpha is our candidate\nsignal of reduced engagement.", 19, MUTED)
text(6.9, 2.95, 5.7, .5, "Research-informed starting point", 21, MINT, True)
text(6.9, 3.55, 5.7, .8, "Related studies evaluate beta/alpha.\nWe use its inverse as an alert feature.", 18, WHITE)
text(6.9, 4.65, 5.7, .5, "Practical for this prototype", 21, MINT, True)
text(6.9, 5.2, 5.7, .8, "Low computation. No labeled training set.\nCompared with a personal baseline.", 18, WHITE)
text(.7, 6.35, 12, .4, "A testable heuristic—not proof that a student stopped paying attention.", 20, AMBER)
text(.7, 6.8, 12, .18, "Research: Coelli et al., 2015, DOI 10.1109/EMBC.2015.7318658. Sources and limitations in backup slides.", 9, MUTED)
finish("Why alpha / beta?", "1:31–1:56 · 25 seconds", "Speaker 2", "")

start(6, "The student value")
text(.65, 1.05, 12, .8, "Less searching. More purposeful review.", 34, WHITE, True)
box(.7, 2.35, 6.75, 3.9)
text(.98, 2.58, 6.1, .35, "ILLUSTRATIVE RECOVERY CARD", 11, MINT, True)
text(.98, 3.18, 6.1, .5, "Neurons · 02:10–02:35", 25, WHITE, True)
text(.98, 4.02, 6.05, 1.1, "Dendrites receive input.\nThe axon carries signals to other cells.", 21, MUTED)
box(.98, 5.35, 5.85, .55, "304958")
text(1.15, 5.47, 5.5, .35, "Quick check: What does an axon do?", 17, MINT)
text(8.15, 2.6, 4.5, .4, "TARGETED", 12, AMBER, True)
text(8.15, 3.03, 4.5, .9, "Review the relevant moment,\nnot a whole lecture.", 21, WHITE)
text(8.15, 4.35, 4.5, .4, "ON THE STUDENT’S TERMS", 12, AMBER, True)
text(8.15, 4.8, 4.5, 1.1, "Student-controlled recovery.\nLocal AI by default.\nHistory they can clear.", 20, WHITE)
text(.7, 6.55, 12, .25, "Working prototype: interval capture, replay, AI explanations, and saved history. Learning impact remains to be tested.", 11, MUTED)
finish("The student value", "1:20–1:50 · 30 seconds", "Speaker 2",
       "Here is the experience we want to deliver: a student misses a short explanation about neurons, then gets a focused recap and a question to check understanding. This illustrative card shows the recovery experience our working prototype supports. AI runs locally by default, and students can clear their recovery history. Our next step is measuring whether that experience improves learning.")

start(7, "The business opportunity")
text(.65, 1.05, 12, 1.3, "Start with one course.\nGrow through campuses.", 38, WHITE, True)
for y, label, value in [
    (2.95, "FIRST USERS", "College students revising recorded STEM lectures"),
    (4.0, "FIRST BUYERS", "Learning-support teams and teaching departments"),
    (5.05, "PROPOSED REVENUE", "Campus software licenses, after pilot validation")]:
    box(.7, y, .05, .7, MINT)
    text(.95, y+.03, 2.9, .35, label, 12, MINT, True)
    text(4.0, y, 8.5, .8, value, 22, WHITE, True)
text(.95, 6.35, 11.5, .5, "Lower the adoption barrier: start with a small pool of loaner headsets.", 21, MUTED)
finish("The business opportunity", "1:50–2:30 · 40 seconds", "Speaker 3",
       "Our proposed first market is college students reviewing recorded STEM lectures, where missing one step can make the next harder. We would start with learning-support teams or teaching departments as pilot partners. Rather than expecting every student to buy a headset, a campus could offer a small loaner pool. If the pilot demonstrates value, we would test campus software licensing as a repeatable business model. The reason to pay is a measurable improvement in the study experience.")

start(8, "The ask")
text(.65, 1.05, 12, 1.35, "Help us turn a working prototype\ninto a better study experience.", 36, WHITE, True)
text(.7, 2.95, 12, .45, "PROPOSED PILOT", 13, MINT, True)
for x, number, label in [(.7, "1", "course partner"), (4.95, "20", "student volunteers"), (9.05, "2", "weeks of use")]:
    text(x, 3.6, 3.6, 1.1, number, 64, MINT, True)
    text(x, 4.95, 3.7, .5, label, 22, WHITE)
text(.7, 5.9, 12, .5, "Measure comprehension, recovery time, and willingness to keep using it.", 20, MUTED)
text(.7, 6.48, 12, .4, "NeuroLearn. Recover the moment. Keep the momentum.", 23, WHITE, True)
finish("The ask", "2:30–3:00 · 30 seconds", "Speaker 3",
       "Our ask is one course partner and twenty student volunteers for a two-week pilot. We would compare the experience with ordinary video review, measuring short comprehension checks, recovery time, and whether students want to keep using it. We have built the recovery flow. Now we want to prove its value in real study sessions. NeuroLearn: recover the moment, keep the momentum. Help us make one missed explanation a recoverable moment, rather than a reason to give up.")

start(9, "Backup / implementation")
slide._element.set("show", "0")
text(.65, 1.05, 12, 1, "The rule behind the attention signal.", 34, WHITE, True)
for x, label, value, body in [
    (.7, "EEG WINDOW", "5 seconds", "First incoming channel; demeaned.\nButterworth filters + filtfilt."),
    (4.95, "CALIBRATION", "10 seconds", "Mean alpha/beta ratio\nduring focused calibration."),
    (9.05, "ALERT RULE", "1.8× baseline", "Above threshold continuously\nfor 5 seconds → alert.")]:
    text(x, 2.65, 3.7, .4, label, 12, MINT, True)
    text(x, 3.25, 3.7, .6, value, 27, WHITE, True)
    text(x, 4.1, 3.7, 1, body, 17, MUTED)
box(.7, 5.3, 11.95, .75, "243B49")
text(.95, 5.48, 11.5, .45, "P = mean(filtered signal²)       R = P_alpha / (P_beta + 10⁻⁹)", 23, MINT, True)
text(.7, 6.35, 12, .5, "Pending starts interval tracking immediately; the alert waits 5 s. Both end when focus returns.", 16, WHITE)
text(.7, 6.8, 12, .18, "Source: current test.py. The multiplier and durations are prototype settings, not clinically validated thresholds.", 9, MUTED)
finish("Backup: signal processing and state logic", "Q&A only · hidden in slideshow", "Any speaker",
       "The current code processes buffer[0], the first incoming channel, in a five-second sliding window. It removes the mean, uses butter(4) bandpass coefficients and filtfilt for alpha 8–13 Hz and beta 13–30 Hz, and estimates power using mean squared filtered amplitude. This is not an FFT-peak ratio; FFT peaks are displayed separately. Calibration averages ratios for ten seconds after a three-second countdown. At or above 1.8 times baseline the app publishes pending; after five continuous seconds it publishes unfocused. The desktop starts timing at pending, not after the alert. The 10-second ratio history is a display history, not the EEG power-estimation window. These numbers describe the current local test.py snapshot and are adjustable engineering choices. Calibration is available but is not enforced as a prerequisite by the app.")

start(10, "Backup / evidence & next steps")
slide._element.set("show", "0")
text(.65, 1.05, 12, 1, "Why this feature—and what comes next?", 33, WHITE, True)
text(.7, 2.35, 5.65, .4, "WHY WE STARTED HERE", 13, MINT, True)
text(.7, 2.95, 5.65, 1.5, "Interpretable and cheap to compute.\nBeta/alpha has been studied in attention.\nIts inverse gives a convenient alert direction.\nA personal baseline gives a local reference.", 18, WHITE)
text(6.95, 2.35, 5.7, .4, "WHAT WE NEED TO VALIDATE", 13, AMBER, True)
text(6.95, 2.95, 5.7, 1.5, "Sensitivity to task, electrode site, and artifacts.\nFalse alerts in real lecture sessions.\nCompare beta/(alpha + theta) and classifiers.\nMeasure against labeled attention checks.", 17, WHITE)
box(.7, 4.95, 11.95, 1.35)
text(.95, 5.12, 11.3, .35, "Research supports investigating EEG ratios—not our exact threshold or learning outcomes.", 17, MINT, True)
text(.95, 5.62, 11.3, .5, "Coelli et al. (2015): beta/alpha during sustained attention; recording sites mattered.\nAhmed et al. (2025): tested several indices; combining features outperformed single indices in their task.", 13, MUTED)
text(.7, 6.5, 12, .5, "References: doi.org/10.1109/EMBC.2015.7318658  |  doi.org/10.3390/s25072072\nNo detection-accuracy claim is made for NeuroLearn.", 11, MUTED)
finish("Backup: scientific rationale and validation", "Q&A only · hidden in slideshow", "Any speaker",
       "Research does not establish alpha as simply distraction or beta as simply focus. Our direction is a working hypothesis. Coelli et al. studied beta/alpha in nine adults performing a continuous-performance task and found montage-dependent relations with reaction time: https://pubmed.ncbi.nlm.nih.gov/26736558/ . Ahmed et al. investigated beta/(theta+alpha), beta/alpha, and inverse alpha in a cognitive-game task: https://pmc.ncbi.nlm.nih.gov/articles/PMC11991241/ . Their beta/alpha index alone did not significantly distinguish game difficulty levels; combined-feature classifiers performed better. Neither paper validates NeuroLearn's first-channel implementation, 1.8 multiplier, five-second persistence rule, or student learning outcomes. A ratio can cancel a common multiplicative amplitude scale in an idealized signal, but does not remove motion, eye or muscle artifacts, or electrode-placement effects. The current code does not implement explicit artifact rejection. Validate signal quality and compare alternative features using independent attention labels before claiming accuracy.")

# Rebalance the main story to exactly three minutes; backup slides are excluded.
main_notes = [
    ("0:00–0:18 · 18 seconds", "Speaker 1", "Have you ever lost focus during a lecture and realized the next explanation no longer makes sense? NeuroLearn helps students recover that missing piece, connecting attention signals with the lecture moment so they can return to learning with context."),
    ("0:18–0:36 · 18 seconds", "Speaker 1", "A brief lapse creates more than lost time. Students lose the thread, search backward, and may still struggle with the explanation. Our opportunity is to make recovery easier before one missed step becomes a bigger learning gap."),
    ("0:36–1:01 · 25 seconds", "Speaker 1", "Our prototype senses a possible lapse, captures the corresponding video timestamps, and offers a choice: replay the segment, ask for an explanation, or continue. The AI uses captions from that interval to summarize the material and offer a review question. The student stays in control."),
    ("1:01–1:31 · 30 seconds", "Speaker 2", "Technically, the board streams EEG into Python. We filter a five-second window into alpha and beta bands, estimate their power, and compare the ratio with a personal calibration baseline. Sustained threshold crossings update the desktop through Flask. The browser records the lecture interval, and local Ollama explains its captions. The attention detector is rule-based; the language model explains the content."),
    ("1:31–1:56 · 25 seconds", "Speaker 2", "Why alpha over beta? Related research has studied beta over alpha as an engagement feature. We use the inverse as an interpretable candidate lapse signal. It is inexpensive to compute, needs no labeled training set, and can be compared with a personal baseline. It is a prototype heuristic that still needs validation."),
    ("1:56–2:16 · 20 seconds", "Speaker 3", "The benefit is targeted review: revisit the relevant moment and get help understanding it. This example card illustrates that experience. Our prototype supports interval capture, replay, explanations, and saved history. Local AI and a clear-history button give students control."),
    ("2:16–2:40 · 24 seconds", "Speaker 3", "We would start with college STEM courses and learning-support teams. A small pool of loaner headsets lowers the adoption barrier. After demonstrating value in a pilot, we would test campus software licensing. The reason to pay is a better study experience, backed by evidence."),
    ("2:40–3:00 · 20 seconds", "Speaker 3", "Our ask is one course partner and twenty volunteers for a two-week pilot. We would compare comprehension, recovery time, and repeat use against ordinary video review. Help us turn a working prototype into a better study experience. NeuroLearn: recover the moment, keep the momentum."),
]
for i, (timing, speaker, script) in enumerate(main_notes):
    title = slides[i][0]
    slides[i] = (title, timing, speaker, script)
    prs.slides[i].notes_slide.notes_text_frame.text = f"{title}\n{timing} | {speaker}\n\n{script}"
prs.save(OUT / "NeuroLearn_3_Minute_Pitch.pptx")
sheet = Image.new("RGB", (1600, 450*((len(previews)+1)//2)), "#09131C")
for i, preview in enumerate(previews):
    sheet.paste(preview.resize((800, 450)), ((i % 2)*800, (i // 2)*450))
sheet.save(OUT / "NeuroLearn_Pitch_Preview.png")
previews[0].save(OUT / "NeuroLearn_3_Minute_Pitch.pdf", save_all=True, append_images=previews[1:], resolution=SCALE)
with (OUT / "Speaker_Script.md").open("w", encoding="utf-8") as f:
    f.write("# NeuroLearn — three-minute pitch\n\nEight main slides plus two hidden technical backup slides. Main timings total 180 seconds. Suggested division: Speaker 1 takes slides 1–3; Speaker 2 takes slides 4–5; Speaker 3 takes slides 6–8. Slides 9–10 are hidden in PowerPoint and are for Q&A only; the PDF includes them. Any group size can use the same timing.\n\n")
    for title, timing, speaker, script in slides:
        f.write(f"## {title}\n\n**{timing} | {speaker}**\n\n{script}\n\n")
    f.write("## Rehearsal tips\n\n- Aim to finish the spoken content by 2:55; use the remaining seconds for handoffs and pauses. Shorten a sentence if rehearsal runs long.\n- Use Presenter View: this script is also embedded in the PowerPoint speaker notes.\n- Skip a live hardware demo in a strict three-minute slot. Offer it after the pitch.\n- The recovery card is illustrative. Do not present it as a captured user result.\n- The pilot size and campus licensing are proposals; there are no claims of existing customers, revenue, or proven learning gains.\n\n## Likely questions\n\n**Does it actually improve grades?**\nWe have a working recovery prototype, not evidence of improved grades. The pilot will measure comprehension and recovery time before making learning-outcome claims.\n\n**Why EEG instead of a rewind button?**\nThe hypothesis is that attention signals can help identify moments worth revisiting without requiring the student to remember exactly when the gap occurred. EEG is an estimate, and users remain in control. The pilot should compare against ordinary video review.\n\n**Will students wear headsets?**\nThat is an adoption question to test. Start with voluntary sessions and loaner devices rather than requiring every student to buy hardware.\n\n**Why would a campus pay?**\nOnly if pilots show useful study outcomes and repeat usage at a workable cost. Campus licensing is a proposed model, not a signed customer commitment.\n\n**What about privacy?**\nThe current default uses local Ollama and local recovery storage. Raw EEG is not sent to the language model. YouTube caption retrieval still needs internet access. There is a clear-history control; that removes recovery history, not separate EEG recordings.\n\n**Can it explain every video?**\nIt currently relies on accessible captions in the configured language. It does not interpret diagrams or independently transcribe audio, and model answers can be wrong.\n")
print(f"Created {len(prs.slides)} slides; {sum(len(s[3].split()) for s in slides[:8])} main-pitch words.")
print(OUT / "NeuroLearn_3_Minute_Pitch.pptx")
