# Contributing to Jupo
If you want to include your code in the general Jupo release, follow these steps:

## Getting started
- Get Jupo running locally, following the [installation guide](Installing-locally)
- Get an account at Github and fork the project Jupo.
- Checkout the edge branch `develop`
- Develop your feature or fix, writing tests where necessary.
- Organize your commits and rebase frequently. [A good guide about this.](http://reinh.com/blog/2009/03/02/a-git-workflow-for-agile-teams.html)

## Submit your bugfix/feature upstream
- Rebase your copy to the latest `develop` branch, make sure it applies cleanly, squash "work-in-progress" commits, and avoid merge, we try to keep our tree linear.
- Run the tests.
- Send a pull request from Github.

## Commits
* Do one commit per change. Don't do two unrelated things in the same commit.
* Put a short, descriptive message on the first line, and then, if necessary, add details in a paragraph after a line break.
* Always explain why you did something, not how.

## Coding style
* Use two spaces for indentation, not tabs.
* Avoid trailing spaces.
* Write tests. Integration testing with cucumber and unit test with rspec.
* Clearness over cleverness. It’s better to write a simple, readable method.
* Avoid long methods. Break them into smaller ones.
* Write fat models, skinny controllers.
* If you write migrations, make sure they are revertible.
* English is the default locale, if you want to provide localized strings in another locale, do it in separate commit.
* Naming convention is important part of making code readable. 
  * Name methods and variables according to what they do. 
  * Follow python conventions
  * Pluralization rules
* Use private methods for things that are not meant to be used by others.

