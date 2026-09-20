"""The files `guardana new-pack` writes, kept as data rather than as string literals.

A template is the text of somebody else's package, including code that would read
wrongly inside this one: a generated test discovers plugins the way a third party's
test does, which is not how a command in this package may. Data cannot be mistaken
for behaviour, by a reader or by the checks that read this directory.
"""
