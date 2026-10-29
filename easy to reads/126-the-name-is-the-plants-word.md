# 126. The name is the plant's word

*A line is refused for what it claims, not for what the plant calls the law. ADR 0329.*

The page refuses a line that says confidence, probability, weight, magnitude,
or score. That is the right refusal. The page should not put a number on how
sure it is.

It was looking in one place too many. Every line starts with the name of the
law it came from, so the page was reading that name as well as the fact. A
plant that calls one of its laws `tank_weight_limit` would never see that law
on the page. Worse, because one bad line withholds the whole call, that one
name would also hide the other broken laws reported with it.

Weight is an ordinary word in a plant. So is magnitude. The plant writes its
own laws, and the page does not get to narrow that list with a word list.

So the page now reads the fact, which is the part the page itself wrote, and
leaves the name alone. A fact that says confidence is still refused, and that
call still shows nothing. A plant law called `tank_weight_limit` can now be
broken, and that break can be read.

Nothing was scored. Version 1 stays at eight of twelve. This is not a result
about a plant.
