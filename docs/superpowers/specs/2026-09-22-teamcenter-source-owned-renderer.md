# Teamcenter source and owned renderer

The Teamcenter model tree is authoritative for the requested model. It currently
stores source selectors and occurrence paths, not copied launchapp URLs or permanent
download URLs. Resolve geometry through the authenticated Teamcenter APIs on open.

## Implemented route

- Teamcenter resolves the selected object to visualization material.
- For DirectModel, resolve its sole JT ImanFile and download it through FMS. Pass
  the actual JT file to the renderer. Retain immutable JT bytes in the private
  content-addressed render cache so deferred geometry reads survive launch cleanup.
- For assembly sources, preserve the Teamcenter-generated VVI, including its
  configured structure references. Do not flatten an assembly into independent JTs.
- Open either material through the retained VisMockup COM application's document
  collection. Do not dispatch an external runner and subsequently discover which
  window received the request. Insert uses the same material preparation pipeline.
- After open, obtain the current runtime document session, embed it, and update the
  environment's runtime association. Keep the Teamcenter source selector unchanged.

## Identity responsibilities

Teamcenter establishes source identity. A runtime process/document handle routes
commands to the loaded renderer and detects a closed/replaced session. Historical
environment document identities and verified-source receipts are not prerequisites
for an explicit new open. No repeated Teamcenter source verification belongs on the
visibility/selection command path.

Repeated part occurrences in assemblies still require distinct instance handles and
transforms. A file URL identifies geometry; it does not identify every occurrence of
that geometry. Resolve that instance mapping once for the current scene and reuse it.

## Validation boundary

Automated tests cover direct renderer open, changed existing documents, JT FMS
handoff, insert, and file retention. Earlier local probes established FMS JT download
and COM JT rendering separately. The newly integrated route has not yet been deployed
or tested end to end against the diagnostic part. Assembly VVI loading through COM
also requires runtime verification. Do not claim measured latency improvements from
the unit tests. JT cache eviction remains a follow-up lifecycle concern; active source
files must not be deleted during renderer use.
