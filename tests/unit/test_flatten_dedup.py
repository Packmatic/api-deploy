from api_deploy.config import Config, ConfigFile
from api_deploy.converters import FlattenProcessor
from api_deploy.schema import Schema, YamlDict

ERROR_RESPONSE = '''
description: Internal Server Error
content:
  application/json:
    schema:
      type: object
      required:
        - message
      properties:
        message:
          type: string
          example: Internal Server Error
'''

URN_SCHEMA = '''
type: string
description: Uniform Resource Name
example: urn:pm:service::foobar/1
'''

EXTERNAL_SCHEMAS = {
    'https://api.example.com/types/responses/500-server-error.yml': ERROR_RESPONSE,
    # Same body, different URL: must collapse into a single component
    'https://api.example.com/types/mirror/500-server-error.yml': ERROR_RESPONSE,
    'https://api.example.com/types/schemas/urn.yml': URN_SCHEMA,
}


class OfflineFlattenProcessor(FlattenProcessor):
    """The real processor fetches external refs over HTTP; serve them from a dict instead."""

    def get_external_schema(self, url):
        return YamlDict(EXTERNAL_SCHEMAS[url])


def build_source(mirror_ref=False):
    second_ref = ('https://api.example.com/types/mirror/500-server-error.yml' if mirror_ref
                  else 'https://api.example.com/types/responses/500-server-error.yml')
    return Schema(f'''
openapi: 3.0.1
info:
  title: Test
  version: '1'
servers:
  - url: http://localhost
tags: []
paths:
  /foo:
    get:
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                type: object
                properties:
                  urn:
                    $ref: 'https://api.example.com/types/schemas/urn.yml'
        '500':
          $ref: 'https://api.example.com/types/responses/500-server-error.yml'
  /bar:
    get:
      responses:
        '500':
          $ref: '{second_ref}'
components:
  schemas: {{}}
''')


def build_processor(dedup_external_refs):
    config = Config(ConfigFile(f'flatten:\n  dedupExternalRefs: {str(dedup_external_refs).lower()}\n'), 'test')
    assert config['flatten']['dedup_external_refs'] is dedup_external_refs
    return OfflineFlattenProcessor(config, **config['flatten'])


def response_schema(schema, path):
    return schema['paths'][path]['get']['responses']['500']['content']['application/json']['schema']


def test_external_refs_are_inlined_by_default():
    processed = build_processor(dedup_external_refs=False).process(build_source())

    for path in ('/foo', '/bar'):
        inlined = response_schema(processed, path)
        assert '$ref' not in inlined
        assert inlined['properties']['message']['type'] == 'string'

    assert processed['components']['schemas'] == {}


def test_dedup_hoists_response_payload_into_components():
    processed = build_processor(dedup_external_refs=True).process(build_source())

    ref = {'$ref': '#/components/schemas/Response500ServerError'}
    assert response_schema(processed, '/foo') == ref
    assert response_schema(processed, '/bar') == ref

    hoisted = processed['components']['schemas']['Response500ServerError']
    assert hoisted['properties']['message']['type'] == 'string'
    assert hoisted['required'] == ['message']

    # The response wrapper itself must stay inline, only the payload schema is shared
    assert processed['paths']['/foo']['get']['responses']['500']['description'] == 'Internal Server Error'


def test_hoisted_component_names_are_api_gateway_safe():
    processed = build_processor(dedup_external_refs=True).process(build_source())

    for name in processed['components']['schemas']:
        assert name.isalnum(), f'{name} is not alphanumeric'
        assert name[0].isalpha(), f'{name} must not start with a digit'


def test_identical_bodies_reached_via_different_urls_collapse():
    processed = build_processor(dedup_external_refs=True).process(build_source(mirror_ref=True))

    assert len(processed['components']['schemas']) == 1
    assert response_schema(processed, '/foo') == response_schema(processed, '/bar')


def test_refs_nested_in_properties_stay_inline():
    processed = build_processor(dedup_external_refs=True).process(build_source())

    urn = processed['paths']['/foo']['get']['responses']['200']['content']['application/json']['schema']
    assert urn['properties']['urn']['type'] == 'string'
    assert '$ref' not in urn['properties']['urn']


def test_dedup_leaves_no_external_refs():
    processed = build_processor(dedup_external_refs=True).process(build_source())

    dumped = processed.dump()
    assert 'https://' not in dumped.replace('http://localhost', '')