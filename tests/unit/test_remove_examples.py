from api_deploy.config import Config, ConfigFile
from api_deploy.converters import ApiGatewayProcessor
from api_deploy.schema import Schema


def build_source():
    return Schema('''
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
      parameters:
        - name: filter
          in: query
          schema:
            type: string
            example: abc
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                type: object
                properties:
                  name:
                    type: string
                    example: Foo
                  example:
                    type: string
                    example: this property is literally named "example"
              examples:
                sample:
                  value: {name: Foo}
components:
  schemas:
    Thing:
      type: object
      example: {a: 1}
      properties:
        a:
          type: integer
          example: 1
''')


def build_processor(remove_examples):
    config = Config(ConfigFile(f'gateway:\n  removeExamples: {str(remove_examples).lower()}\n'), 'test')
    assert config['gateway']['remove_examples'] is remove_examples
    return ApiGatewayProcessor(config, **config['gateway'])


def response_schema(schema):
    return schema['paths']['/foo']['get']['responses']['200']['content']['application/json']


def test_examples_are_kept_by_default():
    processed = build_processor(remove_examples=False).process(build_source())

    assert response_schema(processed)['schema']['properties']['name']['example'] == 'Foo'
    assert processed['components']['schemas']['Thing']['example'] == {'a': 1}


def test_examples_are_removed_when_enabled():
    processed = build_processor(remove_examples=True).process(build_source())

    media = response_schema(processed)
    assert 'example' not in media['schema']['properties']['name']
    assert 'examples' not in media
    assert 'example' not in processed['components']['schemas']['Thing']
    assert 'example' not in processed['components']['schemas']['Thing']['properties']['a']
    assert 'example' not in processed['paths']['/foo']['get']['parameters'][0]['schema']


def test_a_property_named_example_is_never_treated_as_a_keyword():
    processed = build_processor(remove_examples=True).process(build_source())

    properties = response_schema(processed)['schema']['properties']
    assert 'example' in properties, 'a schema property named "example" must survive'
    assert properties['example']['type'] == 'string'
    # ...but its own annotation is still stripped
    assert 'example' not in properties['example']


def test_integration_blocks_are_left_alone():
    processed = build_processor(remove_examples=True).process(build_source())

    integration = processed['paths']['/foo']['get']['x-amazon-apigateway-integration']
    assert integration['type'] == 'http'
    assert integration['responses']['200']['statusCode'] == '200'