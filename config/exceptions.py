import logging

from django.http import JsonResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as default_exception_handler

logger = logging.getLogger("django.request")

ERRORS_BY_STATUS = {
    status.HTTP_400_BAD_REQUEST: (
        "validation_error",
        "The request was invalid. Please check the submitted data.",
    ),
    status.HTTP_401_UNAUTHORIZED: (
        "not_authenticated",
        "Authentication credentials are missing or invalid.",
    ),
    status.HTTP_403_FORBIDDEN: (
        "permission_denied",
        "You do not have permission to perform this action.",
    ),
    status.HTTP_404_NOT_FOUND: (
        "not_found",
        "The requested resource was not found.",
    ),
    status.HTTP_405_METHOD_NOT_ALLOWED: (
        "method_not_allowed",
        "This method is not allowed for the requested resource.",
    ),
}


def exception_handler(exc, context):
    response = default_exception_handler(exc, context)
    if response is not None:
        code, message = ERRORS_BY_STATUS.get(
            response.status_code,
            ("server_error", "An unexpected server error occurred."),
        )
        return Response(
            {"error": {"code": code, "message": message}},
            status=response.status_code,
        )

    request = context.get("request")
    logger.error(
        "Unhandled API exception while processing %s",
        getattr(request, "path", "<unknown path>"),
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return Response(
        {
            "error": {
                "code": "server_error",
                "message": "An unexpected server error occurred.",
            }
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def not_found_view(request, exception=None):
    return JsonResponse(
        {
            "error": {
                "code": "not_found",
                "message": "The requested resource was not found.",
            }
        },
        status=status.HTTP_404_NOT_FOUND,
    )


def server_error_view(request):
    logger.error("Unhandled server error while processing %s", request.path)
    return JsonResponse(
        {
            "error": {
                "code": "server_error",
                "message": "An unexpected server error occurred.",
            }
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
