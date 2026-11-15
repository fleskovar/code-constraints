# code-constraints User Manual

This manual teaches you to use the web app of `cdec`. You start it with one command,
`cdec ui`. After that, you do every task in the browser.

The manual has two main procedures: one for a **brownfield** project (existing code) and
one for a **greenfield** project (new code).

For the commands behind each page, read the [CLI reference](CLI_REFERENCE.md). For a
lesson that uses the command line, read the [tutorial](TUTORIAL.md).

## Contents

1. [Start the web app](#1-start-the-web-app)
2. [The parts of a project](#2-the-parts-of-a-project)
3. [The pages](#3-the-pages)
4. [Choose your path](#4-choose-your-path)
5. [Procedure: a brownfield project](#5-procedure-a-brownfield-project)
6. [Procedure: a greenfield project](#6-procedure-a-greenfield-project)
7. [Task guides](#7-task-guides)
8. [The daily loop](#8-the-daily-loop)
9. [Troubleshooting](#9-troubleshooting)
10. [Quick reference](#10-quick-reference)

---

## 1. Start the web app

1. Open a terminal in the folder of your project.
2. Run `cdec ui`.

The browser opens the home page at `http://127.0.0.1:8765`. The home page has four ways
to open something:

| Choice | Use it when |
|---|---|
| **This folder** | You started `cdec ui` in your project. Select **Open this folder**. |
| **Open a folder** | The code is in another folder. Type the path, or select **Browse…** and choose the folder. |
| **Recent folders** | You opened the folder before. Select the path, or one of its saved views. |
| **Open a model file** | You have a saved diagram (`.xmi` or `.json`) and no source code. |

The app finds the language of the code. If the language is wrong, change it in the
**Language** list before you open the folder. For an empty folder, choose the language of
the code that you plan to write.

A folder opens on its **Project** page. A saved view opens on its diagram.

> **NOTE:** If you work from a clone of `code-constraints`, the `cdec` on your path can be
> an older version. Then run `.venv/Scripts/python.exe -m code_constraints.cli ui`.

> **NOTE:** The app changes files only for requests from your own machine. A web page in
> another browser tab cannot change your rules or read your folders.

---

## 2. The parts of a project

A project in `cdec` has four parts. Each part has a page.

| Part | What it is | Page |
|---|---|---|
| **The codebase** | The folder with your source code. | **Project** |
| **Class diagrams** | Models of the code. A model comes from the code (a snapshot), or you draw it (a target). | **Diagrams** |
| **Constraints and rules** | What the code must obey. A rule is in `.cdec/rules.yaml`. A constraint tag is in the source code. | **Rules** |
| **Check reports** | What the rules report on a model, against a baseline. | **Checks** |

The **Timeline** page shows how these parts changed: the start, each goal, each
checkpoint and each rule change.

### 2.1 Models

Every page names a model in the same way. There are five kinds:

| Model | What it is |
|---|---|
| **The code of today** | The source code as it is on the disk now. |
| **The target** | The reference model in `.cdec/reference.xmi`. It is "the goal" while a goal is open. |
| **A step of the timeline** | The model that the app saved at that step. |
| **A git revision** | The code at a branch, a tag or a commit. |
| **A file** | A model file (`.xmi` or `.json`) that you add. |

You can show any model, compare any two models, and check any model.

### 2.2 Words

| Word | Meaning |
|---|---|
| **Reference** | The saved model that the check compares the code with. |
| **Goal** | A reference that describes code that does not exist yet. It has a name and a reason. |
| **Checkpoint** | A saved step on the way to the goal. |
| **Rule** | One test in `.cdec/rules.yaml`. The check runs all rules. |
| **Constraint tag** | A mark on a class or a method in the source code, for example `sealed`. |
| **Issue** | A fault that a rule reports. Each issue has a key, for example `V-DD3EA5B2`. |
| **Exception** | An issue that you accepted, with a reason. The check no longer fails for it. |
| **Lock** | A frozen implementation. The check fails when the body changes. |
| **Shim** | A small file that makes the tags valid code. `cdec` copies it into the project. |

### 2.3 Files

| File | Content | Who writes it |
|---|---|---|
| `.cdec/rules.yaml` (top part) | Settings and rules | You, and the Rules page |
| `.cdec/rules.yaml` (below the marker line) | Exceptions and lock digests | The tool |
| `.cdec/reference.xmi` | The reference model | The tool |
| `.cdec/history/` | One model and one note for each step of the timeline | The tool |

Commit all of these files. They are the record of your decisions.

---

## 3. The pages

### 3.1 Project

The Project page is the home of a project. It shows:

1. **The codebase**: the path, the language, the number of classes, the git branch.
2. Four cards: **Diagrams**, **Rules**, **Checks**, **Timeline**. Each card opens its page.
3. The **next step** of your journey, with one button.
4. **What do you want to do?** One card for each task. A card opens a wizard or a page.
5. **The steps of the journey**, with a mark on each finished step.

When you do not know what to do, open the Project page and select the next step.

After you change the source code, select **Re-parse** at the top of the window.

### 3.2 Diagrams

The Diagrams page shows a model. The bar at the top has two lists:

- **Show**: the model on the canvas.
- **compared with**: a second model. The canvas then shows the difference.

| Colour | Meaning |
|---|---|
| Green | Only the shown model has it. |
| Red | Only the other model has it. |
| Yellow | Both have it, with different members. |

**Add a model file…** adds a file to both lists.

Examples:

| To see | Show | compared with |
|---|---|---|
| The code | The code of today | nothing |
| What is still to build | The goal | The code of today |
| What the code gained since the start | The code of today | The start step |
| What a branch changes | The code of today | git: main |
| What changed between two steps | The newer step | The older step |

Select **Edit** to change the shown model. See [section 7.1](#71-plan-a-change).

### 3.3 Rules

The Rules page shows what the project demands. It has three tabs:

- **Rules**: each rule of `rules.yaml`. Change the severity, select **Change…** or **Remove**.
- **Constraints in the code**: each constraint tag, with the classes and methods that have it.
- **Locks**: each locked element, and the state of its digest.

### 3.4 Checks

The Checks page runs `cdec check` and shows the result. It has two tabs:

- **Run cdec check**: the run, its options and its result.
- **Accepted issues**: the list of exceptions.

The page runs the check when you open it. Select **▶ Run cdec check** to run it again.
The run is the same as `cdec check` on the command line: the same rules, the same
report and the same exit code. The page shows the command line, with **Copy**.

The options of a run:

| Option | Effect | Command line |
|---|---|---|
| **Fail on** | The severity that makes the exit code 1: `error`, `warning`, or `none` (report only). | `--fail-on` |
| **Rule files** | The files of `.cdec/rules/` to run. Shows only when the rules are in more than one file. | `--rules-file` |
| **More options**, **Check** | The model that the rules read. The default is the code of today. | none for a model |
| **More options**, **against** | The baseline. The rules that look for a change compare with it. | `--reference`, `--base-ref` |
| **More options**, **Bypass the locks** | A changed locked body does not fail the run. A reason is necessary. | `--bypass-locks` |

The result:

- The **banner** shows **Passed** or **Failed**, the exit code, and the number of errors,
  warnings, accepted issues and rules that did not run. Select a number to show or hide
  those issues.
- **Since the run before** shows the issues that are no longer open and the new ones. A
  new issue has the mark **new**. The page keeps the run before while you visit other pages.
- **List** shows each issue with its key, element, file, line and message. Type in the
  filter box to find an issue by key, rule, class, file or message. Use **Group by** to
  group the issues by rule, by element or by file.
- **Text output** shows the text that `cdec check` prints. **Download JSON** saves the
  report of `cdec check --format json`.

The buttons of an issue:

| Button | Effect |
|---|---|
| **Diagram** | Shows the class of the issue on the Diagrams page. |
| **Editor** | Opens the file in your editor, at the line of the issue. |
| **Accept…** | Accepts the issue, with a reason. The page then runs the check again. |
| The key | Copies the key. |

**Show the classes on the diagram** shows every class with an open issue.

You can accept an issue only in the run of the code of today against the reference.

### 3.5 Timeline

The Timeline page shows the steps of the project in a row, oldest first. The last step is
**The code of today**.

| Step | When the app records it |
|---|---|
| **Start** | You create the project config. |
| **Goal** | You set a target model as the goal. |
| **Checkpoint** | You record progress, or you accept the code as the reference. |
| **Rules** | You turn on, change or remove a rule in the app. |

Select a step to see its model on the canvas. The caption shows the title, the reason, the
rules that were on at that step, and what changed since the step before.

- **Play** shows the steps in order.
- The left and right arrow keys move along the row.
- **Colours show** chooses the comparison: the change since the state before, or what is left to reach the goal.
- **Open on the Diagrams page** shows the model of the step alone.
- **Compare with the code of today** shows what the code has and the step does not.

### 3.6 Wizards

A wizard is a short dialog with steps. Use **Back** and **Next** to move between them.
**A wizard writes nothing before its last step.** If you close it early, nothing changes.

| Wizard | Task |
|---|---|
| **Add a rule** / **Change a rule** | Choose a rule, fill in a form, see what it reports, turn it on. |
| **Put a constraint on a class** | Choose a class and a tag. Get the line to paste. Confirm the tag. |
| **Accept the code as the reference** | Make the code of today the new reference. |
| **Run the check automatically** | Get the setup for CI, pre-commit and coding agents. |

`cdec` never edits your source code. When a task needs a change in the code, the wizard
gives you the exact text to paste.

---

## 4. Choose your path

| Your project | Path | First goal |
|---|---|---|
| The code exists. Nobody designed it, or the design drifted. | **Brownfield** | Record the code as it is. Turn on rules one at a time. |
| The folder has little or no code. You design first. | **Greenfield** | Draw the target model. Let the rules keep the code in the plan. |

A project can change path. A brownfield project that plans a big refactor uses the
greenfield steps for that refactor: it draws a target and sets it as the goal.

Both paths use the same four ideas:

1. **Record** the start. The app does this when it creates the project config.
2. **Plan** the target. The target is the goal.
3. **Protect** the plan. Rules fail the check when the code leaves the plan.
4. **Review** the journey. The timeline shows each step on the diagram.

---

## 5. Procedure: a brownfield project

**Goal:** adopt `cdec` on code that exists, with no wall of errors.

**Principle:** record first, enforce later. At each step the check passes. Only new faults fail.

### Step 1. Open the folder and create the project config

1. Run `cdec ui` in the folder of the project.
2. Select **Open this folder**.
3. On the Project page, select **Adopt an existing codebase**.
4. Select **Create the project config**.

The app writes three things:

- `.cdec/rules.yaml` with no rule on
- `.cdec/reference.xmi`, a snapshot of the code of today
- The first step of the timeline, **Start**

The check passes now, because no rule is on.

### Step 2. Look at the code

1. Open the **Diagrams** page.
2. Find the classes that surprise you. Use the search box, the package tree and the **Explore** tools.
3. Select a class to see its details.

Write down the problems that you want to stop. Examples: the domain layer calls the web
layer, two packages depend on each other, one class refers to 30 other classes.

### Step 3. Turn on the first rule

Start with one rule. Choose a rule that protects a boundary that the code already respects.

1. On the Project page, select **Add a rule**.
2. Choose a rule from the gallery.
3. Fill in the form. The name fields suggest the classes and the packages of your project.
4. Select **Try it**. The wizard runs the rule on the code of today. It writes nothing.
5. Read the result.
   - **0 issues:** the rule is safe to turn on.
   - **Some issues:** choose **Accept these**, or choose **Let them fail**.
6. Select **Turn on the rule**.

**Accept these** puts the issues of today into the list of exceptions. The check still
passes. Any new issue of the same rule fails. The list of exceptions is the work that is left.

The timeline gets a **Rules** step for the new rule.

### Step 4. Read the report

1. Open the **Checks** page. The page runs `cdec check`.
2. Read the banner: **Passed** or **Failed**, and the exit code.
3. For each issue, select **Diagram** to see the class, or **Editor** to open the file at the line.
4. If an issue is a real fault, fix the code. Then select **▶ Run cdec check**.
   **Since the run before** shows the issues that you fixed.
5. If an issue is a deliberate choice, accept it with a reason (see [section 7.4](#74-accept-an-issue)).

### Step 5. Add more rules, one at a time

Repeat step 3 and step 4. A good order:

| Week | Add | Why |
|---|---|---|
| 1 | One rule with the severity `warning`. | You collect data. Nothing fails. |
| 2 | Dependency rules, for example `forbidden-package-references` and `no-cyclic-package-dependencies`. | The most common drift. |
| 3 | Tags (`sealed`, `immutable`, `factory`) on the classes that matter, plus `tag-conformance`. | Protects the design inside the classes. |
| 4 | Locks on the few bodies that must not change, plus `implementation-locks`. | Freezes the most important code. |
| Later | `reference-architecture`. | Every structural change becomes a decision. |

If a new rule reports too many issues, do not remove it. Set its severity to `warning` on
the Rules page. Then decrease the number of issues with time.

### Step 6. Plan the refactor

1. On the Project page, select **Plan a change**. The Diagrams page opens in edit mode.
2. Change the model until it shows the structure that you want.
3. Select **Set as goal…**.
4. Enter a name and a reason. The dialog counts the classes that the goal adds, removes and changes.
5. Select **Set as goal**.

The reference is now the goal. The timeline gets a **Goal** step. The source code does not change.

### Step 7. Work toward the goal and record progress

1. Change the code.
2. Select **Re-parse** at the top of the window.
3. Open the **Timeline** page. Select **The code of today**.
4. Read the diagram. Green is still to build. Red is in the code and not in the plan.
5. After each piece of work, select **Record a checkpoint…**. Enter a short title. Select **Record**.

Each checkpoint shows the distance to the goal: the classes to build, to change, and not in the plan.

### Step 8. Close the goal

When the code matches the goal:

1. Open the **Timeline** page. Select **The code of today**.
2. Select **Accept the code as the reference…**.
3. Read the list of classes that join, leave and change.
4. Select **Next**. Enter a name and a reason, for example "Billing split is complete".
5. Select **Make the code the reference**.

The reference is now a snapshot of the code. The goal is closed. The timeline keeps the whole story.

### Step 9. Run the check on every change

On the Project page, select **Run the check automatically**. See [section 7.9](#79-run-the-check-automatically).

---

## 6. Procedure: a greenfield project

**Goal:** design the architecture first. Then use rules to keep the code in the plan while it grows.

**Principle:** the model is the plan. The reference is the plan in a file. The rules enforce the plan.

### Step 1. Open the folder and create the project config

1. Run `cdec ui` in the folder of the project. An empty folder is correct.
2. If the folder has no code, select **Use this path below**. Choose the language. Then select **Open the folder**.
3. On the Project page, select **Start a new design**.
4. Select **Create the project config**.

### Step 2. Draw the target model

1. On the Project page, select **Plan a change**. The Diagrams page opens in edit mode.
2. Add a class: select **+ Add class**. Enter the name and the package.
3. Double-click a class to edit it. Add attributes, operations and base classes.
4. Hover over a class and select **+ attribute** or **+ method** for a quick change.
5. To remove a class, select it and press **Delete**.

The JSON panel at the side shows the same model as text. You can type there. The diagram follows.

Add the constraints to the model at the same time. A class can carry tags: `sealed`,
`immutable`, `no-instantiation`, `factory`, `layer`, `locked`. The tags show as badges on
the diagram.

### Step 3. Set the goal

1. In edit mode, select **Set as goal…**.
2. Enter a name, for example "Order and billing core".
3. Enter the reason. Write why you chose this design. The reason is part of the record.
4. Select **Set as goal**.

Because the code does not exist yet, the whole model is green. The diagram is now a build list.

### Step 4. Turn on the rules that keep the code in the plan

1. On the Project page, select **Add a rule**.
2. Turn on these rules, in this order:

   | Rule | What it protects |
   |---|---|
   | `reference-architecture` | The code must match the goal. A class that is not in the plan fails. |
   | `forbidden-package-references` or `layer-dependencies` | The direction of the dependencies. |
   | `no-cyclic-package-dependencies` | No loops between packages. |
   | `tag-conformance` | The bodies obey the tags, for example `sealed`. |

3. At each rule, select **Try it**. In a new project, the rule reports few issues.

### Step 5. Check the plan

You can check the plan before you write code.

1. Open the **Checks** page. Select **More options**.
2. In **Check**, select the goal.
3. Select **▶ Run cdec check**. Read the report. A plan that breaks a layer rule or has a package cycle shows here.

The rules that read source code do not run on a model. The page lists them as "did not run".

### Step 6. Build

1. Write the code. Use the green classes on the diagram as the list of work.
2. Put the constraint tags in the code (see [section 7.3](#73-put-a-constraint-on-a-class)).
3. Open the **Checks** page. Select **▶ Run cdec check**.
4. Open the **Timeline** page. Select **The code of today**. Green is what is still to build.
5. After each piece of work, record a checkpoint.

When the check fails, there are two cases:

- **The code is wrong.** Fix the code.
- **The plan is wrong.** Change the plan (step 7). Do not accept the issue.

### Step 7. Change the plan

A plan changes while you build. Select **Plan a change** again. While a goal is open, the
editor opens on the goal, not on the code. Your earlier plan stays, and you add to it.
Then select **Set as goal…** and give the new goal a name and a reason.

The timeline keeps both goals. You can compare them on the Diagrams page.

### Step 8. Close the goal

When all classes are built, do [section 5, step 8](#step-8-close-the-goal). Then plan
the next goal.

### Step 9. Run the check on every change

See [section 7.9](#79-run-the-check-automatically).

---

## 7. Task guides

### 7.1 Plan a change

1. On the Project page, select **Plan a change**.
2. Change the model.
3. Select **Set as goal…**. Enter a name and a reason.

To start the plan from another model, open the **Diagrams** page first. In **Show**, select
the model, for example a step of the timeline. Then select **Edit**.

> **NOTE:** A diagram that compares two models cannot become the reference. Set
> **compared with** to "nothing" first.

### 7.2 Add, change or remove a rule

To add a rule:

1. On the Project page or the Rules page, select **Add a rule**.
2. Choose a rule. Fill in the form.
3. Select **Try it**. Read the issues.
4. Select **Turn on the rule**.

Use **Edit as text** if the rule has an option that the form does not show.

To change a rule:

1. Open the **Rules** page. Select the rule to open it.
2. Select **Change…**, or select **Remove**. The app asks you to confirm a removal.
3. To change only the severity, use the list on the row of the rule.

| Severity | Effect |
|---|---|
| `error` | The check fails. |
| `warning` | The check reports the issue and passes. |
| `off` | The rule does not run. |

Two limits:

- A change removes the comments inside that rule entry. Comments before the entry stay.
- If your rules are in `.cdec/rules/*.yaml`, the app shows them but cannot write them.
  Change the file by hand. The tool never writes into `.cdec/rules/`.

### 7.3 Put a constraint on a class

1. On the Project page or the Rules page, select **Put a constraint on a class**.
2. Search for the class or the method. Select it, then select **Next**.
3. Choose the tag, for example `sealed`. Select **Next**.
4. Select **Copy the shim file into the project**. This makes the tag valid code.
5. Copy the import line and the tag line. Paste them into your source file. The wizard can open the file.
6. Select **I wrote the tag**. The wizard parses the code again.
   If the wizard does not see the tag, it stays on the step and tells you why.
7. If the rule that checks the tag is not on, turn it on in the last step.

The tab **Constraints in the code** of the Rules page lists every tag in the project.

### 7.4 Accept an issue

Accept an issue only when the code is correct and the rule is too strict for this one case.

1. Open the **Checks** page. Make sure that the run is the code against the reference.
2. Find the issue. Each issue has a key.
3. Select **Accept…**. Enter the reason.

The issue moves to the tab **Accepted issues**. The reason stays in `rules.yaml` for the
next reviewer.

To accept many issues, type a filter first, for example the name of a rule. Then select
**Accept the N shown issues…**. Use this only to adopt a rule on old code.

A lock issue is different. You cannot accept it as an exception (see [section 7.7](#77-lock-an-implementation)).

### 7.5 Withdraw an accepted issue, and clean the list

1. Open the **Checks** page. Select the tab **Accepted issues**.
2. Select **Withdraw** on an entry. The issue fails the check again.
3. Select **Remove the N stale entries**. This removes the exceptions whose issue no longer occurs.

A short list of exceptions is a sign of a healthy project.

### 7.6 Check against another model

The Checks page can run the rules with other inputs. Select **More options**, choose
the two models, then select **▶ Run cdec check**. These runs change nothing.

| To learn | Check | against |
|---|---|---|
| What `cdec check` reports | The code of today | The reference |
| What a branch adds, compared with `main` | The code of today | git: main |
| What changed since an older snapshot | The code of today | A step of the timeline, or a file |
| If the plan obeys the rules | The goal | The reference |
| If an older state obeyed the rules of today | A step of the timeline | The reference |

To use a model file here, first add it on the Diagrams page with **Add a model file…**.

Select **Reset** to return to the default run.

### 7.7 Lock an implementation

A lock freezes the body of a class or a function. The check fails when the body changes.
Use locks for code that must not change by accident, for example a tax calculation.

1. Open the **Rules** page. Select the tab **Locks**.
2. Select **Lock an element…**. The tag wizard gives the `locked` tag to paste.
3. If the lock rule is not on, select **Turn on the lock rule…**.
4. Select **Record the N new locks**. The app saves the digest of each locked body.

When a locked body changes, the tab shows "the body changed".

- If the change is a mistake, undo it. Then select **Check again**.
- If the change is approved, select **Accept this change…** on that one element.
  The app accepts one named element at a time. It never accepts all changes at once.

> **CAUTION:** Protect `.cdec/rules.yaml` with CODEOWNERS. The `locks:` section is the
> record of approved changes. A review of that diff is the control.

### 7.8 Use the timeline

1. Open the **Timeline** page.
2. Select a step, or use the arrow keys. The canvas shows the model of that step.
3. Select **Play** to see the steps in order. A class keeps its place from step to step.
4. Read **Rules at this step** to see which rules were on.
5. To keep a step for later, select **Record a checkpoint…**.

To see a step on the full Diagrams page, select **Open on the Diagrams page**. There you
can compare it with any other model, or edit it.

### 7.9 Run the check automatically

1. On the Project page, select **Run the check automatically**.
2. Choose where the check runs:
   - **GitHub Actions** or **GitLab CI**: copy the text into your workflow file.
   - **Pre-commit**: copy the text into `.pre-commit-config.yaml`.
   - **A script**: select **Write the two scripts**. The app writes `cdec-ci.sh` and `cdec-ci.bat`.
3. Select **Next**. Read the setup for coding agents. Copy the commands and run them in a terminal.
   The app does not run them.

This is the one task that needs the command line: CI runs `cdec check`, not the web app.
The exit code is not zero when an issue is open.

### 7.10 Open or save a model file

To save the shown model, select **Download XMI** at the top of the window.

To open a model file with no source code:

1. Go to the home page (**Home**).
2. In **Open a model file**, choose the file.
3. To compare two files, choose the second file in **Compare with**.
4. Select **Open the file**.

To compare a file with the code, open the folder. Then use **Add a model file…** on the
Diagrams page.

### 7.11 Move from an older `cdec`

Older versions kept settings in `config.yaml`, `baseline.yaml` and `locks.yaml`. The
Project page shows a message when it finds these files. Select **Fold them in**. The app
moves their content into `rules.yaml` and deletes them.

---

## 8. The daily loop

| When | Do this |
|---|---|
| Before you code | Open the **Timeline** page. Select **The code of today**. Find the next green class. |
| While you code | Open the **Checks** page. Select **▶ Run cdec check**. Read **Since the run before**. |
| After a piece of work | Record a checkpoint on the **Timeline** page. |
| When a rule blocks a good change | Decide: fix the code, change the plan, or accept the issue with a reason. |
| In a pull request | Review the diff of `.cdec/`. Exceptions, locks and goals are the decisions to review. |
| When the goal is complete | **Accept the code as the reference**. Then plan the next goal. |

The three answers to a failed check:

| The problem | The answer | The record |
|---|---|---|
| The code is wrong. | Fix the code. | The commit. |
| The rule is too strict for this one case. | Accept the issue with a reason. | An exception in `rules.yaml`. |
| The plan is wrong. | Edit the model. Set a new goal. | A **Goal** step in the timeline. |

---

## 9. Troubleshooting

| Problem | Cause | Action |
|---|---|---|
| The home page has no **This folder** card. | You opened the app from another machine. | Open the app at `127.0.0.1` on the machine that runs `cdec ui`. |
| **Open this folder** is not there. | The folder has no source code that the app knows. | Choose the language in **Open a folder**, then open the folder. |
| The app does not show a new feature. | The `cdec` on your path is old. | Run `.venv/Scripts/python.exe -m code_constraints.cli ui`. |
| The browser does not open a page. | Another program uses port 8765. | Run `cdec ui --port 8790`. |
| The diagram does not show a change in the code. | The app shows the last parse. | Select **Re-parse**. |
| A new rule reports many issues. | The code already breaks the rule. | Select **Try it**, then **Accept these**. Or set the severity to `warning`. |
| The Rules page cannot change a rule. | The rules are in `.cdec/rules/`. | Change the file by hand. |
| A rule shows "did not run". | The rule needs source code and the checked model has none. Or the rule needs a reference. | Check the code of today. Read the reason on the row. |
| There is no **Accept…** button. | The run is not the code against the reference, or the issue is a lock. | Select **Reset** in **More options**. Accept a lock on the Rules page, tab **Locks**. |
| The tag wizard does not see the tag. | The import line is missing, or the tag is not next to the class. | Make sure that the import line is in the file. Remove empty lines between the tag and the class. |
| A lock fails after a small edit. | The body changed. A comment change does not count. A code change does. | Undo the change, or accept it for that one element. |
| The lists have no git revision. | The folder is not in a git repository. | Use the steps of the timeline, or a model file. |
| "This diagram is a comparison of two models." | You set a comparison as the reference. | Set **compared with** to "nothing". |

---

## 10. Quick reference

### Where each task is

| Task | Page |
|---|---|
| Open a folder, a recent project or a model file | Home |
| Set up a project | Project |
| Find the next step, start any task | Project |
| See the code as a diagram | Diagrams |
| Compare two models | Diagrams, **Show** and **compared with** |
| Draw or change the target | Diagrams, **Edit**, **Set as goal…** |
| Add a rule | Project or Rules, **Add a rule** |
| Change or remove a rule | Rules, tab **Rules** |
| See and add constraint tags | Rules, tab **Constraints in the code** |
| Record or accept locks | Rules, tab **Locks** |
| Run `cdec check`, see why it fails | Checks, **▶ Run cdec check** |
| Check a plan, or check against a snapshot | Checks, **More options** |
| Accept an issue | Checks, the **Accept…** button of the issue |
| Withdraw an accepted issue | Checks, tab **Accepted issues** |
| See the journey of the project | Timeline |
| Record progress | Timeline, **Record a checkpoint…** |
| Close a goal | Timeline, **The code of today**, **Accept the code as the reference…** |
| Set up CI and coding agents | Project, **Run the check automatically** |

The [CLI reference](CLI_REFERENCE.md), section 2.6, gives the command behind each task.

### Not in the web app

- A change of the source code. `cdec` gives you the text to paste.
- The check in CI. CI runs `cdec check` on its own machine. The Checks page runs the same check on your machine.
- The update of `cdec` itself (`cdec update`).
- The bypass for locks (`--bypass-locks`). Use it only in an emergency, from the command line.
- A check with only some of the rule files (`cdec check --rules-file`).
