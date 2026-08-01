"""Load the five long-form articles supplied on 2026-07-31.

Idempotent — matched on slug, so re-running never duplicates and never
overwrites edits made in the admin since.

Two judgement calls worth knowing about, both one line to change:

* `AUTHOR` is "Dare Adebayo". Every one of these is written in the first person
  ("one lesson I have learned"), so the model default of "IADEBAYO Foundation"
  would read wrongly. Correct it here if that attribution is wrong.
* `CATEGORY` is Youth Development for all five, because Category offers only
  that and AI & Entrepreneurship — and neither actually fits articles about SME
  leadership, delegation and scale. See the note the command prints when it
  finishes.

Body format follows Post.body_blocks: a blank line starts a new paragraph, and a
line beginning "## " becomes a subheading. templates/blog/detail.html renders
each block as {{ block.text }} with no linebreaks filter, so the author's short
rhythmic lines ("Later, when revenue improves.") are written as separate
paragraphs — joining them with single newlines would collapse them into one
run-on line in the browser.
"""
import shutil
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from blog.models import Category, Post

AUTHOR = "Dare Adebayo"
CATEGORY = Category.YOUTH

POSTS = [
    {
        "slug": "roi-of-learning-and-development-for-smbs",
        "title": "The ROI of Learning and Development for Small and Medium-Sized Businesses",
        "excerpt": "Many businesses treat learning and development as something to invest in "
                   "later — when revenue improves, when the team grows, when there is more "
                   "time. But waiting comes at a cost, and no business builds capability by "
                   "accident.",
        "seo_title": "The ROI of Learning and Development for SMBs",
        "seo_description": "Why learning and development is not separate from growth for "
                           "small and medium-sized businesses, and what it costs to postpone "
                           "building capability.",
        "body": """Many small and medium-sized businesses treat learning and development as something to invest in later.

Later, when revenue improves.

Later, when the team grows.

Later, when there is more time.

For many founders and business leaders, learning and development is seen as a luxury rather than an essential part of building a sustainable business. When resources are limited, investments are understandably directed toward what appears most urgent—operations, sales, technology, or expansion. Developing people is often placed on a list of important things to revisit when circumstances are better.

But waiting often comes at a cost.

One lesson I have learned from building across different contexts is that businesses rarely outgrow the capabilities of their people by accident. Growth has a way of revealing what a team has not yet learned. Small inefficiencies become larger problems. Knowledge gaps become operational challenges. Processes that worked for five people may no longer work for twenty. Decisions that were once straightforward become more complex as responsibilities expand.

Businesses do not simply grow into new capabilities. They intentionally build them.

Learning and development is not separate from growth. It is part of it.

When conversations about return on investment arise, learning and development can be difficult to defend because its outcomes are not always immediate or easily measured. Unlike revenue targets or quarterly performance metrics, the benefits of investing in people often emerge gradually.

Sometimes the return appears in better decisions being made consistently across teams. Sometimes it is reflected in fewer operational mistakes. Sometimes it is found in improved communication, stronger leadership, or a team member who takes ownership because they were given the opportunity to develop their capabilities.

These outcomes are easy to overlook precisely because they compound quietly over time.

A business may never calculate the financial cost of a poor hiring decision that could have been prevented through better leadership development. It may not measure the opportunities lost because teams lacked the skills or confidence to adapt quickly to change. Likewise, it can be difficult to quantify the value of retaining talented people because they feel invested in and supported in their growth.

Yet these realities shape the long-term health of an organization every day.

Learning creates resilience.

For small and medium-sized businesses especially, resilience matters. Market conditions change. Customer expectations evolve. Technology continues to reshape industries at an unprecedented pace. Businesses that remain relevant are rarely those that simply work harder. They are often those that continue learning faster and adapting more effectively.

This does not always require large budgets or elaborate training programs. Learning can be embedded into the rhythms of an organization. It can take the form of mentorship, peer learning, structured feedback, leadership development, professional certifications, or creating intentional spaces for reflection and improvement.

What matters most is consistency.

Learning should not become something reserved for moments of failure or crisis. It should become part of how the business operates. When development is treated as an ongoing responsibility rather than an occasional initiative, it strengthens systems, improves execution, and makes adaptation possible when circumstances change.

The businesses that endure are often the ones that understand a simple truth: people are not separate from strategy. They are central to it.

Growth may create opportunities, but capability determines whether those opportunities can be sustained.

The question, then, is not whether a business can afford to invest in learning and development. It may be whether it can afford not to.

What capabilities are you intentionally building today that will sustain your business tomorrow?""",
    },
    {
        "slug": "lessons-entrepreneurs-can-learn-from-great-teachers",
        "title": "Lessons Entrepreneurs Can Learn from Great Teachers",
        "excerpt": "Great entrepreneurs and great teachers have more in common than we often "
                   "acknowledge. Neither succeeds by having all the answers. They succeed by "
                   "helping others make progress.",
        "seo_title": "Lessons Entrepreneurs Can Learn from Great Teachers",
        "seo_description": "Leadership is not about being the smartest person in the room. "
                           "What great teachers understand about listening, patience, and "
                           "helping others grow.",
        "body": """One lesson I have learned is that great entrepreneurs and great teachers have more in common than we often acknowledge.

Neither succeeds by having all the answers. They succeed by helping others make progress.

In the early stages of my journey, I believed leadership was largely about making the right decisions quickly. I thought my value was measured by how much I knew, how effectively I could solve problems, and how quickly I could provide direction when challenges emerged.

Experience taught me otherwise.

Over time, I realized that sustainable growth depended less on my ability to provide answers and more on my willingness to listen, explain clearly, and create an environment where others could think, contribute, and improve. Leadership became less about being indispensable and more about helping others become capable.

That, I have come to appreciate, is what effective teachers do every day.

Great teachers understand that learning cannot be rushed. They build understanding patiently. They recognize that people learn differently and adjust their approach without lowering their standards. They provide consistent feedback, create opportunities for growth, and understand that their success is reflected not in what they know but in what others are able to achieve because of what they have taught.

Entrepreneurs can benefit from embracing the same mindset.

Building a business is ultimately about building people, systems, and relationships. Products evolve. Markets change. Strategies are refined. But organizations become sustainable when they are filled with people who are continually learning and growing.

This requires a different understanding of leadership.

It means recognizing that listening is not passive. It is one of the most valuable disciplines a leader can develop. Great teachers listen for misunderstanding before they provide instruction. Similarly, effective entrepreneurs listen carefully to their teams, customers, and changing circumstances before making decisions.

Listening creates clarity. Clarity creates alignment.

When people understand both what is expected of them and why their work matters, they are more likely to take ownership and contribute meaningfully. Teams perform better when expectations are clear. Customers remain loyal when they feel understood. Organizations become more resilient when learning is embedded into their culture rather than being reserved for moments of failure.

Too often, learning becomes reactive. Businesses invest in development only after mistakes have been made or growth has exposed capability gaps. Yet the strongest organizations intentionally create environments where learning is continuous. Reflection is encouraged. Feedback is expected. Improvement becomes part of the organization's rhythm rather than an occasional response to challenges.

Great teachers understand another important truth: progress is often invisible before it becomes obvious.

Learning compounds quietly. Confidence develops gradually. Capability is built over time. The same is true in entrepreneurship. Sustainable growth is rarely dramatic. It is usually the result of small, consistent improvements made patiently over months and years.

Some of the most important work leaders do will never appear in quarterly reports or public announcements. It happens in conversations that build confidence, in feedback that improves performance, and in the time invested in helping others develop their potential.

These investments compound.

I have also learned that great teachers are comfortable with the fact that their students may eventually surpass them in certain areas. They do not see this as a loss of relevance but as evidence that growth has taken place.

Entrepreneurs should aspire to the same outcome.

Leadership is not diminished when others grow in capability. It is strengthened by it. Businesses become healthier when decision-making is distributed appropriately, when people are trusted with responsibility, and when teams are equipped to contribute meaningfully without constant intervention.

The founders who endure are rarely the ones who know the most. They are often the ones who continue learning, continue teaching, and create conditions where other people can grow alongside the business.

Perhaps that is one of the greatest lessons entrepreneurs can learn from great teachers: leadership is not ultimately about being the smartest person in the room. It is about helping others become better because you were there.

What lesson from a great teacher has shaped the way you lead today?""",
    },
    {
        "slug": "the-real-measure-of-scale-is-impact-not-size",
        "title": "The Real Measure of Scale Is Impact, Not Size",
        "excerpt": "Revenue, headcount, visibility, attention — these tell us whether a "
                   "business is growing, but not whether it matters. True scale is measured "
                   "by how deeply the work improves outcomes for the people it serves.",
        "seo_title": "The Real Measure of Scale Is Impact, Not Size",
        "seo_description": "A larger business is not necessarily a more impactful one. Why "
                           "sustainable scale is about becoming better rather than simply "
                           "becoming bigger.",
        "body": """Scale is often measured by size.

Revenue.

Headcount.

Visibility.

Attention.

These metrics are important. They can tell us whether a business is growing, reaching new markets, or attracting interest. But they do not tell the whole story. A larger business is not necessarily a more impactful one, just as a smaller business is not necessarily less significant.

Some of the most impactful businesses remain relatively small, while some large organizations struggle to create meaningful value for the people they serve.

Over time, I have learned that true scale is not about how much noise a business can generate. It is about how deeply its work improves outcomes for customers and how consistently that value can be delivered.

That distinction matters.

Entrepreneurship culture often celebrates what can easily be seen and measured. Funding announcements receive attention. Rapid growth attracts admiration. Expanding teams and impressive revenue figures become visible indicators of success. There is nothing inherently wrong with these milestones. They can represent years of discipline, sacrifice, and thoughtful execution.

The challenge arises when they become our only definition of scale.

A business can grow larger without becoming more valuable. It can become more visible without becoming more meaningful. Growth and impact are related, but they are not always the same thing.

I have learned this through the process of building across different contexts. Growth can create excitement, but it also presents important questions. Are we solving problems more effectively than we did before? Are customers experiencing meaningful outcomes because of our work? Are our systems becoming stronger as we expand? Are we building something that will remain useful and relevant over time?

These questions matter because sustainable businesses are built on more than momentum.

Revenue matters, but it is an incomplete measure of significance.

The return customers experience from engaging with a business often extends beyond what financial statements can reveal. Trust, reliability, consistency, and meaningful outcomes are difficult to capture in a single metric, yet they frequently determine whether a business remains relevant over the long term.

Impact compounds quietly.

A business that consistently solves real problems creates value that extends beyond transactions. Customers return because they trust the experience they will receive. Teams remain engaged because they understand the purpose behind their work. Communities benefit because solutions are designed thoughtfully and delivered responsibly.

This kind of scale is less visible, but it is often more enduring.

There is also an important difference between attention and significance. Attention can be created quickly. Significance must be earned repeatedly. Businesses that pursue visibility without strengthening the value they provide often find themselves scaling expectations faster than they are scaling their capabilities.

When that happens, growth begins to expose weaknesses rather than amplify strengths.

The businesses that endure tend to approach scale differently. They recognize that systems matter as much as strategy. They invest in learning. They listen carefully to customers. They improve incrementally and consistently. Most importantly, they understand that sustainable growth is ultimately measured by the value they create for others.

Scale, then, becomes less about becoming bigger and more about becoming better.

The real measure of scale is not how large a company appears, but how meaningful its contribution remains over time.

As founders and builders, perhaps we should ask ourselves different questions. Instead of asking only how quickly we are growing, we might also ask how deeply we are serving. Instead of measuring what people notice about our businesses, we might consider what people experience because of them.

Because long after attention fades, impact remains.""",
    },
    {
        "slug": "the-difference-between-chasing-traction-and-building-value",
        "title": "The Difference Between Chasing Traction and Building Value",
        "excerpt": "Traction is visible: sign-ups, growth charts, media mentions. Value is "
                   "quieter. Businesses can achieve traction without creating lasting value — "
                   "but sustainable businesses are rarely built without it.",
        "seo_title": "Chasing Traction vs Building Value",
        "seo_description": "Traction asks whether people are coming. Value asks whether they "
                           "have a reason to stay. Why sustainable growth depends on knowing "
                           "the difference.",
        "body": """Many founders confuse traction with value.

It is an understandable mistake. Traction is visible. It appears in growth charts, sign-ups, downloads, customer acquisition numbers, media mentions, and investor interest. It creates momentum and, sometimes, applause.

Value is quieter.

While traction tells us that people have noticed what we are building, value tells us whether we are solving a meaningful problem consistently enough for people to stay, trust us, and return.

The distinction matters because businesses can achieve traction without creating lasting value. Sustainable businesses, however, are rarely built without it.

## What Is the Difference Between Traction and Value?

Traction is often a measure of attention and momentum. It helps founders understand whether there is market interest in what they are building.

Value, on the other hand, is measured differently. It is reflected in customer outcomes, trust, retention, reliability, and the ability to solve real problems consistently over time.

Traction asks whether people are coming.

Value asks whether they have a reason to stay.

Both matter, but they are not interchangeable.

Many businesses focus heavily on acquiring customers while paying less attention to creating experiences that retain them. Growth becomes the primary objective while sustainability becomes an afterthought.

Over time, this imbalance creates challenges that are difficult to ignore.

## Why Founders Often Prioritize Traction

Entrepreneurship naturally rewards visible progress. Revenue milestones are celebrated. User growth attracts attention. Expansion creates excitement.

These indicators are important. They can signal that a business is moving in the right direction.

The danger lies in allowing these metrics to become the only definition of success.

In one season of building, we experienced rapid growth across several important metrics. New users arrived faster than we expected. Interest continued to increase. On paper, the business appeared healthy and promising.

Yet internally, something felt unstable.

Customer engagement was inconsistent. Retention rates were weaker than they should have been. Feedback revealed small but important gaps in the customer experience. While we were celebrating growth publicly, unresolved issues were quietly accumulating behind the scenes.

We had traction.

We had not yet built enough value.

That experience taught me that growth metrics can sometimes conceal underlying weaknesses. Businesses do not become sustainable because they grow quickly. They become sustainable because they grow responsibly.

## Why Sustainable Growth Requires Building Value

The temptation during periods of growth is usually to accelerate everything.

More marketing. More expansion. More announcements.

Slowing down can feel counterintuitive when the numbers are moving in the right direction.

Yet sustainable growth often requires founders to ask difficult questions.

● Are customers experiencing meaningful outcomes?

● Are they returning consistently?

● Are our systems strong enough to support growth?

● Are we solving the right problem well enough?

● Can we deliver the same quality as we scale?

These questions shift the focus from visibility to durability.

At one point, we deliberately chose to focus less on acquisition and more on depth. We listened more carefully to customers. We refined processes internally. We improved reliability. We clarified the problem we were truly solving and removed distractions that did not contribute meaningfully to customer outcomes.

Growth slowed temporarily.

But something more valuable happened.

Retention improved. Trust strengthened. Referrals became more organic. Revenue became more predictable. Most importantly, the business felt sturdier.

The foundations became stronger.

## How Businesses Create Long-Term Value

Building value is rarely dramatic. More often, it is the result of small and consistent decisions made over time.

It requires founders to:

● Listen carefully to customers.

● Prioritize reliability over novelty.

● Strengthen systems before accelerating growth.

● Make difficult decisions about what not to pursue.

● Choose long-term credibility over short-term excitement.

Value creation is ultimately an exercise in discipline.

It means resisting the pressure to scale faster than your capabilities allow. It means understanding that saying "not yet" can sometimes be more strategic than saying "yes."

Businesses that endure are not necessarily the ones that grow the fastest. They are often the ones that solve meaningful problems repeatedly and consistently.

## Sustainable Growth Is Built on Value

Traction is about attention.

Value is about impact.

One can be manufactured temporarily. The other must be earned consistently.

Founders need both. The challenge is ensuring that traction becomes the outcome of value creation rather than a substitute for it.

Sustainable growth is rarely dramatic. It is usually the result of solving real problems well, strengthening systems patiently, and remaining committed to the people being served.

Perhaps the most important question for founders is not how quickly their numbers are growing today. It is whether the value they are creating will still matter years from now.

Because while traction may introduce customers to a business, value is what gives them a reason to remain.

The businesses that endure understand the difference.""",
    },
    {
        "slug": "what-founders-learn-too-late-about-delegation-and-trust",
        "title": "What Founders Learn Too Late About Delegation and Trust",
        "excerpt": "One of the quietest reasons companies stall is that founders struggle to "
                   "let go. Control feels responsible — until it becomes the bottleneck that "
                   "limits everything you are trying to build.",
        "seo_title": "What Founders Learn Too Late About Delegation",
        "seo_description": "Delegation is not transferring tasks, it is transferring "
                           "responsibility with clarity. Why businesses scale through trust "
                           "rather than through control.",
        "body": """One of the quietest reasons companies stall is this: founders struggle to let go.

In the early stages of building a business, control feels responsible. You know the vision better than anyone else. You understand the customer. You have carried the weight of difficult decisions from the beginning. Delegation can feel less like leadership and more like lowering standards.

For many founders, remaining involved in everything feels like commitment.

I believed that for longer than I should have.

Over time, I learned that one of the greatest challenges of entrepreneurship is recognizing when your greatest strength has become your greatest limitation. The habits that help founders build businesses are not always the same habits that help them scale them.

Sometimes, growth requires founders to become less involved in the day-to-day so they can become more effective where they are needed most.

## Why Do Founders Struggle to Delegate?

Founders rarely struggle with delegation because they are unwilling to trust people. More often, they struggle because they care deeply about what they are building.

Control provides reassurance. When every important decision passes through the founder, quality feels protected. Problems appear easier to manage because they remain visible and familiar.

However, control can quietly become a bottleneck.

In one phase of growth, I found myself involved in nearly every meaningful decision. Approvals flowed through me. Final reviews landed on my desk. Team members waited for direction instead of exercising judgment. I told myself I was protecting quality.

In reality, I was slowing the company down.

The business did not need more of my presence. It needed clearer ownership.

That realization changed how I thought about leadership.

## What Is Effective Delegation?

Many people think delegation simply means assigning tasks to others. In practice, effective delegation is far more intentional than that.

Delegation is not about transferring tasks. It is about transferring responsibility with clarity.

That requires clearly defined outcomes, measurable standards, and the patience to allow people to learn. It requires creating environments where expectations are understood and accountability is possible.

Most importantly, it requires trust.

Trust is not built through speeches or organizational announcements. It is built through consistent alignment, honest feedback, and repeated opportunities for people to demonstrate ownership.

Without these foundations, delegation often feels risky because it becomes difficult to distinguish between empowerment and ambiguity.

## Why Trust Matters When Scaling a Business

At first, letting go feels uncomfortable. Mistakes happen. Decisions are made differently than you would have made them. Progress may even feel slower in the beginning.

That discomfort is part of scaling.

If every meaningful decision depends on the founder, the company eventually becomes constrained by one person's bandwidth. Decisions become delayed. Teams become overly dependent. Growth creates increasing pressure rather than increasing capability.

That is not leadership. It is a bottleneck.

Trust becomes particularly important as organizations grow because businesses do not scale through founders working harder. They scale by developing the capacity of the people around them.

A founder's responsibility is not simply to build products or services. It is also to build people, systems, and structures that allow excellence to be sustained over time.

## How Can Founders Delegate More Effectively?

I learned that proper delegation begins long before a task is handed over.

It starts with designing roles clearly. It requires documenting processes thoughtfully and establishing review rhythms that create accountability without creating unnecessary dependence. Feedback loops must become intentional rather than occasional.

When systems are strong, trust becomes easier.

When expectations are vague, frustration multiplies.

Delegation should never mean abandoning standards. Instead, it should create clarity around what excellence looks like and provide people with the support necessary to achieve it consistently.

Founders often underestimate how much of effective delegation happens before responsibility changes hands.

The goal is not simply to reduce workload. It is to increase organizational capability.

## The Long-Term Benefits of Delegation

Over time, I began to notice important changes.

Team members took greater ownership of their responsibilities. Decisions became faster because they no longer required unnecessary approval processes. I regained time to think strategically instead of reacting operationally. Most importantly, the organization grew in capability, not merely in size.

Delegation strengthened the business because it strengthened the people within it.

This is perhaps one of the most overlooked returns on effective leadership. Businesses become more resilient when knowledge is distributed appropriately and responsibility is shared intentionally.

Delegation is not a loss of control. It is an investment in collective strength.

## Leadership Beyond Control

Founders often learn this lesson later than they expect because control feels safe. Yet safety can quietly limit growth when it prevents others from contributing meaningfully.

Leadership eventually becomes less about doing the work yourself and more about creating the conditions for others to do meaningful work well.

Businesses that endure are rarely dependent on the extraordinary efforts of one individual. They are supported by clear systems, capable people, and cultures where ownership is encouraged and developed consistently.

The real question, then, is not whether you can do something better yourself.

It is whether you are building a structure where others can do it well without you.

Because sustainable businesses do not scale through control. They scale through trust, clarity, and the deliberate development of people who are capable of carrying the vision forward.""",
    },
]

# Excerpt is a TextField and seo_* are CharFields, so SQLite will not complain if
# a future edit runs long — it would just publish silently truncated metadata.
# Check here instead, before anything is written.
LIMITS = {"excerpt": 300, "seo_title": 70, "seo_description": 160}

# Cover images, slug -> filename under static/img/blog/.
#
# Shipped in static/ (tracked by git) and copied into MEDIA_ROOT on load, the
# same trick seed_demo uses for the gallery: cover_image is an ImageField, so it
# has to resolve under MEDIA_ROOT, but a file only in media/ would not survive a
# fresh deploy. Sources and licence are recorded in static/img/blog/CREDITS.md.
#
# These are stock stand-ins chosen to match the subject of each piece. Swap any
# of them by dropping a new 16:9 file in and re-running with --refresh-covers.
COVERS = {
    "roi-of-learning-and-development-for-smbs": "learning-and-development.webp",
    "lessons-entrepreneurs-can-learn-from-great-teachers": "great-teachers.webp",
    "the-real-measure-of-scale-is-impact-not-size": "impact-not-size.webp",
    "the-difference-between-chasing-traction-and-building-value": "traction-vs-value.webp",
    "what-founders-learn-too-late-about-delegation-and-trust": "delegation-and-trust.webp",
}

# seed_demo's two placeholder articles. Matched on slug *and* the stub author, so
# if someone has since rewritten the post at one of these slugs into something
# real, it is left alone rather than deleted.
DEMO_SLUGS = ["why-learn-entrepreneurship", "ai-for-founders-2026"]
DEMO_AUTHOR = "IADEBAYO Foundation"


class Command(BaseCommand):
    help = "Create the five long-form blog posts supplied on 2026-07-31."

    def add_arguments(self, parser):
        parser.add_argument(
            "--draft", action="store_true",
            help="Create them unpublished, so they can be reviewed in the admin first.")
        parser.add_argument(
            "--refresh-covers", action="store_true",
            help="Re-copy the cover images even for posts that already exist. Use "
                 "after swapping a file in static/img/blog/.")
        parser.add_argument(
            "--drop-demo", action="store_true",
            help="Delete seed_demo's two placeholder articles. Irreversible — only "
                 "touches those slugs, and only while they still carry the stub author.")

    def attach_covers(self, refresh):
        """Copy static/img/blog/*.webp into MEDIA_ROOT and point the posts at them.

        Only fills a blank cover_image unless --refresh-covers is passed, so a
        cover uploaded through the admin is never silently overwritten.
        """
        blog_dir = Path(settings.MEDIA_ROOT) / "blog"
        blog_dir.mkdir(parents=True, exist_ok=True)
        attached = missing = 0
        for slug, filename in COVERS.items():
            src = Path(settings.BASE_DIR) / "static" / "img" / "blog" / filename
            if not src.exists():
                self.stderr.write(self.style.WARNING(
                    f"  ! cover missing from static/img/blog/: {filename}"))
                missing += 1
                continue
            posts = Post.objects.filter(slug=slug)
            if not refresh:
                posts = posts.filter(cover_image="")
            if not posts.exists():
                continue
            shutil.copy(src, blog_dir / filename)
            attached += posts.update(cover_image=f"blog/{filename}")
        return attached, missing

    def drop_demo_posts(self):
        """Remove seed_demo's placeholders, guarded on the stub author."""
        doomed = Post.objects.filter(slug__in=DEMO_SLUGS, author_name=DEMO_AUTHOR)
        titles = list(doomed.values_list("title", flat=True))
        doomed.delete()
        kept = Post.objects.filter(slug__in=DEMO_SLUGS)
        return titles, list(kept.values_list("slug", flat=True))

    def handle(self, *args, **options):
        for entry in POSTS:
            for field, cap in LIMITS.items():
                if len(entry[field]) > cap:
                    self.stderr.write(self.style.ERROR(
                        f"{entry['slug']}: {field} is {len(entry[field])} chars, cap is {cap}."))
                    return

        publish = not options["draft"]
        # First in the list gets the newest timestamp: Post.Meta orders by
        # -published_at, so the list page reads in the order supplied.
        base = timezone.now()
        created = skipped = 0

        for index, entry in enumerate(POSTS):
            _, was_created = Post.objects.get_or_create(
                slug=entry["slug"],
                defaults={
                    "title": entry["title"],
                    "excerpt": entry["excerpt"],
                    "body": entry["body"],
                    "seo_title": entry["seo_title"],
                    "seo_description": entry["seo_description"],
                    "author_name": AUTHOR,
                    "category": CATEGORY,
                    "published": publish,
                    "published_at": base - timedelta(minutes=index),
                },
            )
            if was_created:
                created += 1
                words = len(entry["body"].split())
                self.stdout.write(f"  + {entry['title']}  ({words} words)")
            else:
                skipped += 1

        attached, missing = self.attach_covers(options["refresh_covers"])
        if attached:
            self.stdout.write(f"  {attached} cover image(s) attached")

        state = "published" if publish else "as drafts"
        self.stdout.write(self.style.SUCCESS(
            f"\n{created} created {state}, {skipped} already present."))

        if options["drop_demo"]:
            removed, kept = self.drop_demo_posts()
            for title in removed:
                self.stdout.write(f"  - removed placeholder: {title}")
            if not removed:
                self.stdout.write("  no placeholder articles found to remove")
            for slug in kept:
                self.stdout.write(self.style.WARNING(
                    f"  ! kept {slug} — author is no longer \"{DEMO_AUTHOR}\", so it "
                    f"looks rewritten. Delete it in the admin if it really is a stub."))
        elif Post.objects.filter(slug__in=DEMO_SLUGS, author_name=DEMO_AUTHOR).exists():
            self.stdout.write(self.style.WARNING(
                "\n  seed_demo's two placeholder articles are still published. "
                "Re-run with --drop-demo to remove them."))

        if created:
            self.stdout.write(self.style.WARNING(
                f"\nWorth reviewing in the admin, under Posts:\n"
                f"  · Author is set to \"{AUTHOR}\" on all {created} — the articles are "
                f"written in the first person, so the\n"
                f"    \"IADEBAYO Foundation\" default would read wrongly. Change it if that "
                f"is not right.\n"
                f"  · Category is \"{Category(CATEGORY).label}\" on all {created}, because "
                f"that and \"AI & Entrepreneurship\" are the\n"
                f"    only choices the model has. Neither really fits articles on SME "
                f"leadership and scale;\n"
                f"    adding a third choice to blog.models.Category would need a migration.\n"
                f"  · No cover images. Cards and social previews fall back to the site "
                f"default until one is uploaded."))
