Version Numbers
There are three numbers in a Jupo version:

<major version number>.<release number>.<revision number>

The second number, the release number, indicates release stability. An odd release number indicates a release in a development series. Even numbered releases indicate a stable, general availability, release.

Additionally, the three numbers indicate the following:

<major version number>: This rarely changes. A change to this number indicates very large changes to Jupo.
<release number>: A release can include many changes, including new features and updates. Some changes may break backwards compatibility. See release notes for every version for compatibility notes. Even-numbered release numbers are stable branches. Odd-numbered release numbers are development branches.
<revision number>: This digit increments for every release. Changes each revision address bugs and security issues,
Example Version numbers:
1.0.0 : First stable release
1.0.x : Bug fixes to 1.0.x. These releases carry low risk. Always upgrade to the latest revision in your release series.
1.1.x : Development release. Includes new features not fully finished and other works-in-progress. Some things may be different than 1.0
1.2.x : Second stable release. This is a culmination of the 1.1.x development series.