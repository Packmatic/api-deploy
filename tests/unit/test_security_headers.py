from api_deploy.config import Config, ConfigFile
from api_deploy.processors.security_headers_processor import SecurityHeadersProcessor
from api_deploy.schema import Schema


def build_source():
    return Schema('''
openapi: 3.0.1
info:
  title: Test
  version: '1'
paths:
  /foo:
    get:
      responses:
        '200':
          description: OK
        '404':
          description: Not found
      x-amazon-apigateway-integration:
        type: http
        responses:
          default:
            statusCode: '500'
          '200':
            statusCode: '200'
            responseParameters:
              method.response.header.Access-Control-Allow-Origin: "'foo.com'"
          '404':
            statusCode: '404'
    options:
      responses:
        '200':
          description: '200'
      x-amazon-apigateway-integration:
        type: mock
        responses:
          default:
            statusCode: '200'
''')


def process(source):
    config = Config(ConfigFile(''), 'test')
    return SecurityHeadersProcessor(config).process(source)


def test_every_backend_response_returns_hsts_and_nosniff():
    get_endpoint = process(build_source())['paths']['/foo']['get']

    for status_code in ('200', '404'):
        assert get_endpoint['responses'][status_code]['headers'].keys() == {
            'Strict-Transport-Security',
            'X-Content-Type-Options',
        }
        integration_response = get_endpoint['x-amazon-apigateway-integration']['responses'][status_code]
        response_parameters = integration_response['responseParameters']
        hsts_mapping = response_parameters['method.response.header.Strict-Transport-Security']
        assert hsts_mapping == "'max-age=31536000; includeSubDomains'"
        assert response_parameters['method.response.header.X-Content-Type-Options'] == "'nosniff'"


def test_existing_header_mappings_are_kept():
    get_endpoint = process(build_source())['paths']['/foo']['get']

    response_parameters = get_endpoint['x-amazon-apigateway-integration']['responses']['200']['responseParameters']
    assert response_parameters['method.response.header.Access-Control-Allow-Origin'] == "'foo.com'"


def test_status_codes_the_method_does_not_declare_are_skipped():
    get_endpoint = process(build_source())['paths']['/foo']['get']

    assert 'responseParameters' not in get_endpoint['x-amazon-apigateway-integration']['responses']['default']
    assert '500' not in get_endpoint['responses']


def test_cors_preflight_mocks_are_left_alone():
    options_endpoint = process(build_source())['paths']['/foo']['options']

    assert 'headers' not in options_endpoint['responses']['200']
    assert 'responseParameters' not in options_endpoint['x-amazon-apigateway-integration']['responses']['default']
