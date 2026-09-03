"""Agent 5 — Scope guard. See docs/agents.md §5.

Query path, every turn, first step. Fails closed on ambiguity — the tie-break order
(distress > practical_support > greeting > out_of_domain > answerable) is what makes
"ambiguous routes to the more restrictive category, not silently to answerable" (§7.1)
enforceable rather than aspirational.

There is no diagnostic-refusal category anymore. Earlier this asked the system to refuse
outright ("do I have ADHD" -> a flat "this system can't diagnose you" message) — dropped
by explicit instruction: a question about whether symptoms match a condition's criteria is
just as answerable from the literature as any other evidence question, as long as the
answer stays a description of what the literature/diagnostic criteria say in general,
never a personal verdict about the specific person asking ("you have/don't have X"). That
constraint lives in the translator (which strips the personal narrative before anything
downstream ever sees it — §7.2) and the writer (which only ever writes from those scrubbed
chunks, so it structurally has no personal information to diagnose someone WITH) — not in
a refusal here. "do I have ADHD", "does this sound like autism to you" are answerable.

practical_support exists because a flat out_of_domain boundary message is a dead end for
a real, non-research need clearly tied to being autistic/ADHD/etc. — workplace rights,
discrimination, education accommodations, benefits — that isn't itself a literature
question but shouldn't just bounce with nothing. Real testing case: "I am autistic and
need guidance about the law on office harassment" is not researchable and not distress by
itself, but a bare "that's not what I cover" response is a worse failure than pointing to
real, named organizations that actually handle this — and pipeline.py runs the SAME
research pipeline underneath regardless, attaching resources alongside a citation-backed
answer whenever one exists, never instead of it.

greeting was originally a plain-code keyword match (no model call) — dropped after real
testing showed it fails on anything not in its exact list ("hy" instead of "hi" fell
through to out_of_domain). Folded into this same classification call instead: the model
already has to read the message anyway, and recognizing a greeting — typos, variants, and
all — is exactly the kind of judgment call a keyword list can't make but a model can.

Runs on gpt-4o, not the gpt-4o-mini used everywhere else in this system — a deliberate,
isolated exception. Real, controlled testing (identical prompt, only the model changed)
found gpt-4o-mini reliably misclassifying plain, unambiguous grief/loss statements ("I
lost my cat", "I just lost my cat") as distress, 3/3 on every phrasing tried, and two
increasingly explicit prompt rewrites — including listing that exact phrase as a named
non-example — did not fix it. gpt-4o got every one of the same test cases right with the
identical prompt. This isn't a wording problem; it's model-specific behavior on this one
judgment call, and distress is the working spec's own "highest-risk terminal state in the
system" (§9.2) — not a place to keep tuning prompts around a smaller model's limitation.
No latency cost either: gpt-4o measured faster than gpt-4o-mini on this exact call in the
same test.
"""

from enum import Enum

from pydantic import BaseModel

from neurodiversity.agents.base import AgentResult, run_agent

PROMPT_VERSION = "v9"

SYSTEM_PROMPT = """Classify this message into exactly one category:

- answerable: a question researchable against the neurodevelopmental research literature
  (autism, ADHD, dyslexia, dyspraxia, Tourette's, and related conditions). This includes
  BOTH a question about a treatment, program, or claim's legitimacy ("I have ADHD, is
  there evidence this £1200 program actually cures it?", "should I treat my ADHD for
  $1000") AND a question asking whether the person (or someone they describe) might have a
  condition, or whether their symptoms match diagnostic criteria — "do I have ADHD", "does
  this sound like autism to you", "am I dyslexic based on X" are ALL answerable too, not a
  separate refused category. The system never tells someone what they personally are or
  aren't (that constraint is enforced downstream, in how the answer gets written — not by
  refusing to look at the question at all): every version of this question gets a real,
  literature-backed answer describing what the criteria/evidence actually say, framed
  generally, never as a personal verdict about the specific person asking.
- distress: requires an AFFIRMATIVE signal of danger to the person — explicit or strongly
  implied self-harm, suicidal ideation, or language stating they cannot go on / cannot
  cope / it's not worth continuing. This is a bright-line, mechanical test, not a
  judgment call about how sad a message sounds: if no such signal is present, the message
  is NOT distress, full stop — this is never an ambiguous or close call, and the general
  "prefer the more restrictive category when ambiguous" rule below does not apply to it,
  because there is no ambiguity to resolve. Grief, sadness, loss, frustration, or
  exhaustion — about anything, including a pet, a job, a relationship, or life in general
  — is NOT distress by itself, no matter how emotionally loaded the wording is, unless an
  actual danger signal (as defined above) is also present. Examples that are NOT
  distress: "I lost my cat", "I just lost my cat", "I lost my job and I'm devastated",
  "everything feels so hard right now", "I'm exhausted and don't know how much more I can
  take of this week" (venting/exhaustion, not danger). Examples that ARE distress: "I
  don't want to be here anymore", "I can't do this anymore, what's the point of going
  on", "I've been thinking about ending things". When in doubt, the absence of an
  explicit or strongly implied danger signal means classify as something else entirely
  (out_of_domain, practical_support, or answerable, per the message's actual content) —
  do not round an ordinary sad statement up to distress "to be safe."
- practical_support: a real, practical need connected to being autistic/ADHD/dyslexic/
  dyspraxic/having Tourette's that is NOT researchable against the literature and NOT a
  request for diagnosis — workplace rights or discrimination, harassment, bullying or
  social exclusion, education accommodations, benefits or disability support, and similar
  life-practical questions where an actual organization or support pathway could plausibly
  help. An explicit diagnosis disclosure is NOT required to fire this category — this
  system's entire audience is neurodivergent people, their families, or people supporting
  them, so a bare, contextless statement naming one of THESE SPECIFIC problem types
  (bullying/exclusion, workplace conflict/discrimination, school/education difficulty,
  benefits/disability access) is presumed connected without needing an explicit "I am
  autistic" first. e.g. "I was bullied" is practical_support with practical_topic "general"
  (or "education"/"workplace" if the message says where).
  This does NOT extend to generic sadness, grief, exhaustion, loneliness, or venting with
  no named problem type of that kind — "I am so sad", "I lost my cat", "I feel awful today"
  are NOT practical_support (there is no organization or resource that answers a bare
  emotion), and are NOT distress either absent a danger signal (see distress's own
  definition) — these fall through to out_of_domain, where a normal, warm conversational
  reply is the right response, not a resource list. The test is: does the message name a
  concrete problem category this system actually has a support pathway for? If yes,
  practical_support. If it's just an unanchored feeling with nothing to act on, it isn't.
  When practical_support fires, also set practical_topic to whichever of these fits best:
  "workplace", "education", "benefits", or "general" (use "general" only if none of the
  other three clearly fits, e.g. bullying/exclusion with no stated setting).
- greeting: the ENTIRE message is just a greeting or pleasantry with no other content —
  "hi", "hello", typos/variants of these ("hy", "helo"), "how are you", "thanks", "bye" —
  and nothing else is being asked. A greeting attached to a real question is NOT this
  category — "hi, what does the literature say about X" is answerable, not greeting,
  because there's a real question to answer. Only classify as greeting when there is
  nothing else to respond to.
- out_of_domain: recipes, weather, sports scores, tech support, trivia, general hobbies,
  and similar topics with no human-development, behavioral, social, or life-difficulty
  angle at all — AND also generic, unanchored feelings or venting with no named problem
  this system could act on ("I am so sad", "I lost my cat", "I feel awful today"; see
  practical_support's own definition for that boundary and why). This is a narrow bucket
  in the sense that it must not be used to dodge a genuinely researchable or practical
  question just because it lacks an explicit diagnosis label — a message naming a real,
  concrete problem this system covers (bullying, workplace/education difficulty,
  discrimination, benefits access, or a real evidence question) is NOT out_of_domain
  merely for omitting "I am autistic/ADHD/etc." (route it to practical_support or
  answerable instead, whichever fits). A vague statement with truly no topic at all ("does
  it work" with nothing to anchor it) belongs to answerable, not out_of_domain, so the
  next step can ask a clarifying question. But a message with no named topic AND no
  concrete problem at all — just an unanchored emotion — is genuinely out_of_domain: there
  is nothing to research and nothing to point a resource at, so a plain conversational
  reply is the correct response, not a forced categorization.

If the message is ambiguous between categories, prefer the more restrictive one in this
order: distress > practical_support > greeting > out_of_domain > answerable. This does not
make a stated diagnosis ambiguous by itself — ambiguity means genuine uncertainty about
which category fits, not the mere presence of a personal disclosure alongside an otherwise
clear, researchable question. It also does not make a bare unanchored feeling (see above)
ambiguous — that's a clean out_of_domain case, not a close call to resolve toward
practical_support.

You may be given prior conversation context — a running summary and/or the last few
exchanges. Use it to resolve a short follow-up that has no content on its own — e.g. if
the prior exchange was about whether pets play a different role in autistic people's
lives, and the new message is just "what research says about it", classify that as
answerable, using the established topic as the referent for "it". A follow-up with no
topic of its own is not automatically out_of_domain; check the context first. If the new
message is already a complete, standalone message, ignore the context and classify it
as normal — do not let a prior topic pull an unrelated new message into its category."""


class ScopeClassification(str, Enum):
    answerable = "answerable"
    distress = "distress"
    practical_support = "practical_support"
    greeting = "greeting"
    out_of_domain = "out_of_domain"


class PracticalTopic(str, Enum):
    workplace = "workplace"
    education = "education"
    benefits = "benefits"
    general = "general"


class ScopeResult(BaseModel):
    classification: ScopeClassification
    practical_topic: PracticalTopic | None = None


def classify(raw_input: str, context_summary: str = "", recent_turns: list[tuple[str, str]] | None = None) -> AgentResult:
    """context_summary/recent_turns: same shape as translator.translate's and
    general_chat.reply's — short-term session memory. Real testing found scope_guard was
    the one classification step in the pipeline that never received this, so a
    contentless follow-up ("what research says about it") was judged completely blind to
    the established topic and defaulted to out_of_domain even when the prior exchange had
    made the topic perfectly clear."""
    user_message = raw_input
    if context_summary or recent_turns:
        context_block = ""
        if context_summary:
            context_block += f"Summary of earlier conversation: {context_summary}\n\n"
        if recent_turns:
            context_block += "Recent exchanges:\n" + "\n".join(
                f"- {q}" + (f" ({r})" if r and r != q else "") for q, r in recent_turns
            ) + "\n\n"
        user_message = f"{context_block}New message: {raw_input}"

    return run_agent(
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        output_model=ScopeResult,
        prompt_version=PROMPT_VERSION,
        # No model= override — uses run_agent's gpt-4o default. See module docstring for
        # why this one agent is a deliberate exception to the gpt-4o-mini tiering used
        # everywhere else: a real, reproducible gpt-4o-mini failure on distress detection.
        temperature=0.0,
    )
