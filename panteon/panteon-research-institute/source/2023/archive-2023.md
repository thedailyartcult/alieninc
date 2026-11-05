---
title: Static Tests, Living Systems — A Critique
tag: Panteon Research Institute
topic: Evaluation
date: 2023-12-31
author: Patrick Neil A.
slug: static-tests-living-systems
locked: true
---

# Static Tests, Living Systems — A Critique

## The Static Assumption

Every test is a snapshot. It captures a moment in time, a specific set of conditions, a particular configuration of the system being tested. The assumption behind every test is that this snapshot is representative — that what is true at the moment of testing is true more broadly, and that the conditions of the test are the conditions in which the system will actually operate.

This assumption is almost never true for complex systems. Complex systems are not static. They evolve, they adapt, they respond to their environment, and they change in ways that are difficult to predict and harder to capture in a fixed test. A test that measures a system today may not measure the same system tomorrow, because the system has learned, adapted, or been modified in response to the test itself.

This is the static assumption: the assumption that a test captures a stable, representative property of a system that is, in fact, dynamic, adaptive, and context-dependent. The static assumption is the deepest flaw in the testing practices of machine intelligence, and it is the flaw that most evaluation research has not yet addressed.

## Living Systems

A living system is a system that changes in response to its environment, its inputs, and its own history. Living systems are not just complex; they are adaptive. They learn from experience. They adjust their behavior based on feedback. They evolve.

Machine intelligence systems are living systems. They are trained on data that reflects a particular moment in time, but they operate in environments that are constantly changing. They adapt to new inputs, they respond to new patterns, and they change in ways that their creators did not anticipate and cannot fully predict. A language model trained on text from 2022 is not the same system in 2024, because the world it operates in has changed, the data it encounters has changed, and the model itself has been updated and modified.

Testing a living system with a static test is like testing a river with a cup. The cup captures a sample, but the sample is not the river. The river is moving, changing, responding to rainfall and season and the landscape it flows through. The cup gives you one measurement at one moment, and if you mistake that measurement for the river, you will be systematically wrong about what the river is and what it will do.

## The Feedback Problem

The feedback problem is the mechanism by which static tests fail to capture living systems. When a system is tested, the test produces a result. The result is used to evaluate the system, to compare it to other systems, and to make decisions about what to build next. But the result also changes the system — or changes the incentives that shape what gets built next.

When a benchmark becomes a target, researchers optimize for the benchmark. When researchers optimize for the benchmark, the systems they build become better at the benchmark but may not become better at the things the benchmark was supposed to measure. The system adapts to the test, and the test no longer measures what it was supposed to measure. This is the feedback problem, and it is the reason why benchmarks in machine intelligence have a half-life: they stop measuring what they were designed to measure after a short period of optimization pressure.

The feedback problem is not a bug in the testing process. It is a feature of the interaction between living systems and static tests. As long as the systems being tested are adaptive and the tests are static, the feedback problem will persist. The only solution is to design evaluation methods that account for the living nature of the systems being evaluated — methods that test not just a snapshot but a trajectory, not just a performance level but a capacity for adaptation.

## Toward Dynamic Evaluation

Dynamic evaluation is an approach to testing that takes the living nature of complex systems seriously. Instead of asking "how does this system perform on this test?", dynamic evaluation asks "how does this system change over time, in response to different environments, and under different pressures?"

Dynamic evaluation has three characteristics that distinguish it from static testing.

**First, it tests trajectories, not snapshots.** Instead of measuring a system at a single point in time, dynamic evaluation measures how the system changes over time — how it adapts, how it degrades, how it responds to new challenges. A trajectory is a richer and more honest picture of a living system than a single snapshot.

**Second, it tests in changing environments.** Static tests use fixed environments — fixed datasets, fixed conditions, fixed assumptions. Dynamic evaluation uses changing environments — datasets that evolve, conditions that shift, assumptions that are challenged. This reveals how the system responds to change, which is the defining characteristic of a living system.

**Third, it tests for robustness, not just performance.** Performance is what a system does when conditions are favorable. Robustness is what a system does when conditions are not favorable — when the input is unexpected, the environment is adversarial, or the system encounters a situation it has never seen before. Robustness is the quality that matters most for living systems, because living systems must operate in a world that is not designed for them.

## The Limits of Testing

The limits of testing are not a reason to stop testing. They are a reason to test more honestly, more rigorously, and more humbly. Every test is an instrument, and every instrument has limits. The goal is not to build a perfect test — that is impossible — but to build tests that are honest about their limits, that reveal as much as they conceal, and that are used in service of understanding rather than optimization.

Static tests will continue to have a role in the evaluation of machine intelligence. But they should no longer be the primary lens. The primary lens should be dynamic evaluation — a set of methods that take the living, adaptive, changing nature of these systems seriously, and that ask questions worthy of that complexity.
