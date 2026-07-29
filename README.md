# API Deploy

Compile an OpenAPI spec into an Amazon API Gateway definition and deploy it.

Packmatic fork of [fabfuel/api-deploy](https://github.com/fabfuel/api-deploy). Published
privately as `packmatic-api-deploy` to the `packmatic` AWS CodeArtifact domain.

## Install

```bash
aws codeartifact login --tool pip \
  --domain packmatic --domain-owner 038513119918 \
  --repository packmatic --region eu-central-1

pip install packmatic-api-deploy
```

For local development, pipx keeps the `api` CLI isolated:

```bash
pipx uninstall api-deploy            # remove the upstream build first, the `api` binary collides
pipx install packmatic-api-deploy --pip-args="--index-url $(aws codeartifact get-repository-endpoint \
  --domain packmatic --domain-owner 038513119918 --repository packmatic \
  --format pypi --region eu-central-1 --output text)simple/"
```

## Usage

```bash
api compile <config> <source> <target>   # compile only
api deploy <config> <api-id> <stage> <source>
```

## Configuration

```yaml
gateway:
  integrationHost: 'https://${stageVariables.host}'
  connectionId: '${stageVariables.connectionId}'
  removeScopes: true          # strip OAuth scopes; API Gateway rejects them
  removeDescriptions: true    # strip `description` from components/schemas
  removeExamples: true        # strip `example` / `examples`
flatten:
  dedupExternalRefs: true     # share resolved external $refs instead of copying them
headers:
  request: [Authorization, Content-Type]
cors:
  origin: '*'
static:
  files: [api.v1.yml]
strict:
  enabled: true
  overwriteRequired: true
  blocklist: [_links, _meta]
generator:
  languages: [typescript]
  output: src/openapi/types
```

`removeExamples` and `dedupExternalRefs` both default to `false`, so existing configs
compile byte-for-byte as before.

### `flatten.dedupExternalRefs`

API Gateway's `put-rest-api` / `import-rest-api` body limit is
[6 MiB](https://docs.aws.amazon.com/apigateway/latest/api/API_PutRestApi.html#API_PutRestApi_RequestBody).
By default every external `$ref` is resolved into a **full inline copy** at each use site, and
YAML anchors are disabled, so a spec that shares a handful of error responses across a few
hundred endpoints inflates enormously — Packmatic's spec inlined ~1,100 copies of the same
six error schemas.

With `dedupExternalRefs: true`, each resolved external schema is registered once under
`components/schemas` and every use site becomes an internal `$ref`. API Gateway resolves
internal `#/components/schemas/*` refs, so the result imports unchanged.

Scope: refs in a `schema:` position, and the payload schema of any resolved object carrying
`content` (responses, request bodies). The response *wrapper* stays inline — only the payload
schema is shared. Refs nested inside `properties` are still inlined, as are parameter refs,
which API Gateway requires inline.

Component names derive from the ref filename, forced to be alphanumeric and to start with a
letter (`responses/500-server-error.yml` → `Response500ServerError`), and are uniquified
against existing components. Schemas with identical bodies collapse into one component even
when reached through differently spelled refs.

Effect on Packmatic's packaging spec: **6,364,377 B → 4,214,757 B**, or 3,915,048 B with
`removeExamples` as well. API Gateway model count drops from ~1,214 to ~128, since identical
models are shared rather than duplicated per use site; per-method validation is unchanged.

### `gateway.removeExamples`

Strips `example` and `examples`. A schema *property* literally named `example` is preserved —
only keyword positions are stripped — and `x-amazon-apigateway-integration` blocks are left
untouched. Note this runs before the CORS processor, so CORS response-header examples it
generates afterwards remain.

Do not enable it in a config that also has a `generator` section: the TypeScript generator
emits `Example:` JSDoc from these values, so the generated types would lose those comments.
Keep it in the API-Gateway-only config.

## Releasing

Releases are published manually by a developer, not by CI. The flow is:

1. open a PR with your change
2. get it approved and merged into `develop`
3. from `develop`, publish the package:

```bash
./scripts/release.sh                 # interactive
./scripts/release.sh --bump patch    # or non-interactive
./scripts/release.sh --bump none     # publish the current version as-is
```

The script runs the unit tests, builds sdist + wheel in a throwaway venv, authenticates
to CodeArtifact with your own AWS credentials, and uploads. It bumps
`api_deploy/__init__.py` only — no git tag or commit — so commit that bump yourself
afterwards.

Then pin the new version where it is consumed, e.g. `packaging`'s
`.github/workflows/deployment.yml`.

## Development

```bash
pip install . -r requirements-test.txt
pytest
flake8 api_deploy
```

The functional tests resolve external `$ref`s against the live schemas at
`api.packmatic.io` / `api-staging.packmatic.io`, which are served from the
[api-types](https://github.com/Packmatic/api-types) repo. When api-types changes a shared
schema, `tests/openapi/*_target.yml` goes stale and must be regenerated — api-types 1.11.0
widened the `urn.yml` pattern to support two ids and added fields to the error responses,
which is why those fixtures were refreshed.