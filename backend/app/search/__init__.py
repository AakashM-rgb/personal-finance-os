"""Natural-Language Financial Search.

Architecture (never bypassed - see app.search.service):

    Authenticated user
        -> Search API (app.api.v1.search)
        -> NL interpreter (app.search.interpreter) - produces ONLY a
           validated app.search.schemas.FinancialSearchQuery
        -> app.search.query_builder - maps that query onto the same
           predefined, allowlisted TransactionFilters the rest of the app
           already uses
        -> app.services.transaction_service (existing, authorized)
        -> database

Natural-language interpretation never produces executable SQL, an ORM
expression, or a dynamically-chosen repository/table/function name. Every
field on FinancialSearchQuery is a plain typed value (a date, an integer
amount, an enum member, a bounded list of day-of-week integers) -
there is no generic {field, operator, value} triple anywhere in this
package, so interpreted text has no way to express an arbitrary filter.
"""
