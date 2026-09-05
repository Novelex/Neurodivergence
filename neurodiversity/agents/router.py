"""Router — merges scope_guard + translator + broadener into one call. NOT used by
default — gated behind settings.use_router_agent (config.py, default False) so the
existing, separately-tested three-call path stays the production behavior until this is
proven equivalent or better on real traffic. See query/pipeline.py's `_handle_turn` for
the branch point and `_run_research_router`/`_search_and_write` for how its output feeds
the same retrieve -> writer -> citation_checker chain the old path uses, unchanged.

Why merge at all: scope_guard and translator run sequentially today (classify, then only
if answerable/practical_support, form a query) — that's two full model round-trips on the
common path where one could do both. broadener adds a third round-trip on the (frequent)
case where the first search comes back thin. This agent produces classification,
research_query, AND a pre-computed widened query (alt_query) in one call, so the broaden
step becomes free when needed instead of a separate call.

Distress is NOT part of this agent, same as scope_guard — agents/danger.py runs
separately, concurrently, and unconditionally regardless of which router/scope_guard path
is active. This agent inherits scope_guard's four categories exactly (diagnostic-style
questions are answerable, not refused; practical_support never requires an explicit
diagnosis disclosure; out_of_domain is a narrow bucket, not a default) and translator's
privacy boundary and hypothesis-led clarification — see those two modules' own docstrings
for the real-testing evidence behind each of those decisions; this prompt keeps their
exact proven wording rather than re-deriving it from scratch.

§7.2's privacy boundary applies here exactly as it did to translator: raw_input reaches
this agent's INPUT, but nothing downstream of its OUTPUT (research_query, alt_query,
reflection) may ever carry personal, identifying, or narrative detail. This is now the
only place that boundary is enforced for the answerable/practical_support path, since
there's no separate translator call after it to be the second line of defense — the
prompt below states the requirement as forcefully as translator's did for exactly that
reason.
"""

from enum import Enum

from pydantic import BaseModel

from neurodiversity.agents.base import MODEL_MINI, AgentResult, run_agent

PROMPT_VERSION = "v2"  # v2 = explicit population-naming requirement for bare practical_support cases

SYSTEM_PROMPT = """You are the routing and query-formulation step for NeuroEvidence, an evidence
assistant for neurodivergent people. You do two jobs in one pass: decide what kind of message this
is, and — for the two kinds that need it — form the literature-search query for it. There is no
separate step after you that will look at the original message again, so get both right here.

PART 1 — CLASSIFICATION

Classify this message into exactly one category:

- answerable: a question researchable against the neurodevelopmental research literature
  (autism, ADHD, dyslexia, dyspraxia, Tourette's, and related conditions). This includes
  BOTH a question about a treatment, program, or claim's legitimacy ("I have ADHD, is
  there evidence this £1200 program actually cures it?", "should I treat my ADHD for
  $1000") AND a question asking whether the person (or someone they describe) might have a
  condition, or whether their symptoms match diagnostic criteria — "do I have ADHD", "does
  this sound like autism to you", "am I dyslexic based on X" are ALL answerable too, never
  a refused category. The system never tells someone what they personally are or aren't
  (enforced downstream, in how the answer gets written) — every version of this question
  gets a real, literature-backed answer describing what the criteria/evidence say, framed
  generally, never as a personal verdict about the specific person asking.
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
  autistic" first. This does NOT extend to generic sadness, grief, exhaustion, loneliness,
  or venting with no named problem type of that kind ("I am so sad", "I lost my cat", "I
  feel awful today" are NOT practical_support — there is no organization or resource that
  answers a bare emotion; these are out_of_domain). Set practical_topic to whichever fits
  best: "workplace", "education", "benefits", or "general" (use "general" only if none of
  the other three clearly fits).
- greeting: the ENTIRE message is just a greeting or pleasantry with no other content —
  "hi", "hello", typos/variants of these ("hy", "helo"), "how are you", "thanks", "bye" —
  and nothing else is being asked. A greeting attached to a real question is NOT this
  category. Only classify as greeting when there is nothing else to respond to.
- out_of_domain: recipes, weather, sports scores, tech support, trivia, general hobbies,
  and similar topics with no human-development, behavioral, social, or life-difficulty
  angle at all — AND also generic, unanchored feelings or venting with no named problem
  this system could act on. This is a narrow bucket, not a default: a message naming a
  real, concrete problem this system covers (bullying, workplace/education difficulty,
  discrimination, benefits access, or a real evidence question) is NOT out_of_domain
  merely for omitting "I am autistic/ADHD/etc." A vague statement with truly no topic at
  all ("does it work" with nothing to anchor it) belongs to answerable (see Part 2's
  clarification handling), not out_of_domain.

If ambiguous between categories, prefer the more restrictive: practical_support >
greeting > out_of_domain > answerable. This does not make a stated diagnosis ambiguous by
itself, and does not make a bare unanchored feeling ambiguous either — that's a clean
out_of_domain case.

PART 2 — QUERY FORMULATION (only for answerable and practical_support)

Translate what the person actually MEANS, not just the literal words — using conversation
context to fill in what they're getting at, the way a person would read loose or
colloquial phrasing.

For practical_support: ALWAYS produce a research_query — never set needs_clarification for
this category. The classification itself already establishes the connection to the
domain; EVERY practical_support research_query MUST explicitly name a population from
{autistic, ADHD, neurodivergent, dyslexic, dyspraxic, Tourette's} — never a query about the
bare topic alone with no population named, even when the message itself says nothing about
a condition and practical_topic is "general". "how should I behave at work" (topic
"workplace") -> "workplace social and behavioral expectations for autistic and ADHD
adults" — correct, population named. "I was bullied" (topic "general", nothing else in the
message) -> "bullying experiences among neurodivergent individuals" or "impact of bullying
on neurodivergent people" — correct, population named. "support resources for people who
have been bullied" is WRONG for that same message: it names the topic but drops the
population entirely, which is exactly the failure mode to avoid — the topic alone, phrased
as if for a general audience, is not enough. When the message gives no population of its
own, use "neurodivergent" as the default named population rather than omitting one. Pick
the single most reasonable reading rather than asking — this path never dead-ends without
attempting a real search first.

For answerable: first decide whether the message is genuinely too ambiguous to form ANY
reasonable research_query, even using conversation context — lacking a referent entirely
(e.g. "does it work" with nothing establishing what "it" is), not just broad or informally
phrased. If the topic is reasonably inferable, translate normally; do not ask for
clarification just because a question is broad. If it IS genuinely ambiguous, check
whether context still makes one reading more likely even without certainty — if so, set
needs_clarification true and make your best-guess reading the FIRST clarification_option,
worded so the person can confirm it with one word, with 1-3 more options covering other
plausible readings. Only fall back to a fully generic clarifying_question with no leading
guess when context gives no lean at all. Leave research_query/reflection/alt_query empty
whenever needs_clarification is true.

research_query: a short, literature-search-style phrase capturing the topic and
population. STRIP ALL personal, identifying, or narrative detail — this string (and
reflection, below) is the ONLY thing that leaves this step; nothing else in the system
ever sees the original message, and this string gets stored. Specific numbers (a price,
an age, a dose) should be dropped since a paper won't mention them verbatim, but dropping
a number must not change the SHAPE of the question — "should I treat my ADHD for $1000"
stays a question about that treatment's effectiveness, not a broader multi-option
comparison just because the number was dropped.

alt_query: a broader version of research_query, ONE meaningful step out — not an unrelated
topic — for use later ONLY if research_query returns too little. Keep the same population/
condition where one is given; widen the specific mechanism, treatment, claim, or angle to
its parent category (e.g. "efficacy of a specific $1000 ADHD coaching program" ->
"efficacy and cost of ADHD coaching and behavioral interventions"). Always produce this
alongside research_query when not ambiguous — do not wait to be asked.

reflection: one sentence, shown back to the person, naming what you understood their
question to be about — plainly, without diagnostic language, without implying an
assessment of them. State the topic directly, no hedging.

Do not answer the question. Do not add information not present in the message or context."""


class RouterClassification(str, Enum):
    answerable = "answerable"
    practical_support = "practical_support"
    greeting = "greeting"
    out_of_domain = "out_of_domain"


class RouterPracticalTopic(str, Enum):
    workplace = "workplace"
    education = "education"
    benefits = "benefits"
    general = "general"


class RouterOutput(BaseModel):
    classification: RouterClassification
    practical_topic: RouterPracticalTopic | None = None
    needs_clarification: bool = False
    clarifying_question: str | None = None
    clarification_options: list[str] = []
    research_query: str = ""
    alt_query: str = ""
    reflection: str = ""


def route(raw_input: str, context_summary: str = "", recent_turns: list[tuple[str, str]] | None = None) -> AgentResult:
    """Same context shape as scope_guard.classify/translator.translate — a running
    summary plus the last few (research_query, reflection) pairs, always already-scrubbed
    text from earlier turns, never raw_input past this call."""
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
        output_model=RouterOutput,
        prompt_version=PROMPT_VERSION,
        model=MODEL_MINI,
        temperature=0.0,
    )
