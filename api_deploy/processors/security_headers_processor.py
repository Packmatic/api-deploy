from api_deploy.config import Config
from api_deploy.processors.abstract_processor import AbstractProcessor
from api_deploy.schema import Schema


class SecurityHeadersProcessor(AbstractProcessor):
    """Adds HSTS and nosniff to every backend response. API Gateway only returns headers mapped per response,
    so the ones the load balancer sets never reach clients."""

    security_headers = {
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
        'X-Content-Type-Options': 'nosniff',
    }

    def __init__(self, config: Config, **kwargs) -> None:
        pass

    def process(self, schema: Schema) -> Schema:
        for path in schema['paths']:
            for method in schema['paths'][path]:
                endpoint = schema['paths'][path][method]
                integration = endpoint.get('x-amazon-apigateway-integration', {})
                # CORS preflight mocks answer from API Gateway itself and never reach the backend.
                if integration.get('type') != 'http':
                    continue

                method_responses = {str(status_code): response for status_code, response in endpoint['responses'].items()}
                for integration_response in integration['responses'].values():
                    method_response = method_responses.get(str(integration_response['statusCode']))
                    # Without a declared method response for this status code there is nothing to attach the header to.
                    if method_response is None:
                        continue

                    method_response_headers = method_response.setdefault('headers', {})
                    response_parameters = integration_response.setdefault('responseParameters', {})
                    for header_name, header_value in self.security_headers.items():
                        method_response_headers[header_name] = {'schema': {'type': 'string'}}
                        response_parameters[f'method.response.header.{header_name}'] = f'\'{header_value}\''

        return schema
