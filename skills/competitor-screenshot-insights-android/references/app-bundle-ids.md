# Android App Package Registry

This table is the verified cache for an explicitly named app's launch target. Do not manually select a package name, infer a brand from a company name, reuse the foreground session, or inspect the installed-app list to choose a launch target.

On Android the `Bundle ID` column holds the **application package name** (for example `com.example.travel`). The column keeps its name so one parser and one manifest schema serve both platforms; the value is always what the device reports for the package, never an iOS bundle identifier.

Use `sh scripts/open-mapped-app.sh` for every named-app launch. It first accepts only an exact App value or explicit Alias from this table. If no entry exists, it alone may query the phone's installed-app inventory: only one exact display-name match is eligible. It opens that discovered package, captures a launch screenshot, and requires the installed name, foreground package, and visible application label to agree before automatically appending a mapping and writing a target manifest. No match, duplicate display name, or identity mismatch is a hard stop.

The automation may append a previously unknown mapping only after this complete verification. Do not manually add, change, or delete mappings during research. Treat corrections to an existing mapping as a separate, user-authorized maintenance task.

This table ships **empty on purpose.** Android package names are not derivable from the iOS bundle identifiers of the same brands, and an unverified guess here would defeat the identity gate that is supposed to catch a wrong-app launch. Every row below is earned on-device by the discovery flow above.

| App | Bundle ID | Visible brand | Aliases | Verified |
|---|---|---|---|---|
