## Moving Target Section

**The change I am answering: cut the cost budget by 40 percent.**

Cost is already at $0.0065 for the whole 455 event batch, about $0.0000143 per event amortized
across all 455, a 97.7 percent cut from the naive way of doing it. So this specific budget cut
is already met today without changing anything. The real version of this question is what
happens once volume grows toward the 50,000 events a day number mentioned in the assignment,
where doing it the naive way would get expensive fast.

**What I would turn off first: nothing in the filtering or grouping I already built.** Those are
already free. The thing I would actually change is which model handles a brand new type of
message the system has never seen before. Right now 10 message patterns cover the incident
volume in this file. The cost only really shows up when a genuinely new kind of log line comes
in that has not been grouped yet. For that case, I would try a cheaper model first, and only
call in a stronger model if the cheap one comes back unsure. This is safe to do because the
system already sends unsure answers to a human instead of guessing, and that safety net worked
correctly in my testing, zero wrong guesses across all 455 events.

**What this costs in accuracy: basically nothing for message patterns I already know.** Those
keep their current accuracy on the labeled set, since they are matched against something
already seen, not reasoned out fresh each time. The only place accuracy could soften a little is
on a brand new message pattern running through the cheaper model for the first time, until
either the safety net catches it and sends it to a person, or enough of that new message shows
up that it becomes its own known pattern and gets classified once, cheaply, like everything
else.

**The other version of this question: what if speed needed to drop to 1.5 seconds instead of 4.**
Based on what I actually measured, I do not think this is possible without a real change in how
the system is built, not just a setting I can flip. Digging into the trace data showed that a
good chunk of the total time happens before the model even starts working, and that did not
change when I swapped to a different model. Getting down to 1.5 seconds would likely mean moving
off the hosted Lyzr platform entirely and running the model somewhere closer, which is a
different architecture, not a quick fix. I would tell the customer this plainly rather than try
to squeeze a gap that big out of settings alone, since my own testing showed that does not work.
