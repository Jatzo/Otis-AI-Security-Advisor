"""Answering from retrieved evidence, and checking the answer against the store.

The plan this follows is docs/generation-plan.md. The model writes an answer and the claims it
rests on. Code reads every fact from the store and either lets the answer through, cuts out an ID
the evidence never held, or refuses the whole reply.
"""
