from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """
    Default page size 20; clients may ask for a different size with
    ?page_size=N (the admin users page requests 10 per page).
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
