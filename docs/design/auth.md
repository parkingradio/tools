# Auth

The tool acts on a site as an admin, through the site's MCP server, as an app of its own, "Parking Radio CLI": the admin
connects it from their browser, with OAuth, as the site's
[OAuth](https://github.com/parkingradio/website/blob/main/docs/design/server/oauth.md) design describes. Its
`client_id` is `https://parking.radio/oauth/parkingradio-cli.json`, whatever the site. Below, `<site>` is the site's
address (see [Site](README.md#conventions)).

## `parkingradio auth login`

Connects the tool to the site:

1. It gets the site's authorization server metadata, `<site>/.well-known/oauth-authorization-server`, and checks that
   its `issuer` is `<site>`. When it isn't, the command fails and gives the address that the site has as its own. When
   the site can't be reached, or doesn't answer with that document, it fails too, before the browser is involved.
2. It listens for the browser on `127.0.0.1`, on a port the system chooses, and sends the browser to
   `<site>/autoriser`, the site's authorization page, with:
   - `response_type` `code`, and `client_id` above,
   - `redirect_uri` `http://127.0.0.1:<port>/callback`,
   - `code_challenge`, the S256 PKCE challenge of a new random verifier, and `code_challenge_method` `S256`,
   - `scope` `admin`,
   - `state`, a new random value,
   - `resource` `<site>/mcp`.

   It opens that address in the default browser, and also shows it, with what to do, in case the browser doesn't
   open, or isn't the one where the admin is logged in.
3. It waits for the browser to come back to `redirect_uri` with the same `state`. Requests to other paths, or without
   that `state`, get an error, and are otherwise ignored. When none comes back after 5 minutes, the command fails,
   and says that if the site's page showed an error, that's why: the site doesn't send the browser back for some of
   them (see
   [Authorizing an app](https://github.com/parkingradio/website/blob/main/docs/design/server/oauth.md#authorizing-an-app)).
4. The answer, once it has that `state`, has to have `iss` set to `<site>`, or the command fails. When it has `error`,
   the command fails with it: with `access_denied`, it says that the admin refused. Otherwise, it exchanges its `code`
   at `<site>/api/oauth/token`, with `grant_type` `authorization_code`, `code`, `client_id`, `redirect_uri`,
   `code_verifier` and `resource`. The browser's page, as plain text, says to go back to the terminal, or why the tool
   can't connect.
5. The site's answer has to have `token_type` `Bearer` (in any case), an `access_token`, a `refresh_token`, and
   `expires_in`, or the command fails. It keeps the tokens (see [Credentials](README.md#conventions)), with when the
   access token expires and the connection's `scope`, and says that it's connected.

Before step 1, it checks that it can use the credential store, so that it doesn't make a connection it can't keep.
When it can't keep the new tokens anyway, it revokes the new connection, and fails. When the command fails, the tool
keeps what it had. When the tool was already connected to the site, the new connection replaces the previous one, which
the tool then revokes, like `auth logout` does: when that fails, it says so as a warning, and still succeeds.

## `parkingradio auth status`

Says whether the tool is connected to the site, and whether the connection works. When the tool has the site's tokens,
it sends MCP's `initialize` to the site's MCP server, as described in [Using the connection](#using-the-connection),
with `protocolVersion` `2025-11-25`, `capabilities` `{}`, and `clientInfo`, the tool's name, `parkingradio`, and
version. When that succeeds, it shows the site's address, the MCP server's name, which says which environment the site
is (see [The endpoint](https://github.com/parkingradio/website/blob/main/docs/design/server/mcp.md#the-endpoint)), and
the connection's scopes, and exits with 0. When the tool isn't connected to the site, it says so on stdout, with
`parkingradio auth login` to run, and exits with 1. When the connection doesn't work, the command fails, and says why,
e.g. that the connection ended.

It doesn't show which admin the connection acts as, or when it will end: the site's Admins page does, under "Vos
applications connectées".

## `parkingradio auth logout`

Ends the connection: it revokes the refresh token at `<site>/api/oauth/revoke`, with `token` and `client_id`, then
deletes the site's tokens, and says so. When the revocation fails, e.g. because the site can't be reached, it still
deletes them, but fails, and says that the connection may still exist, and how to end it from the site's Admins page.
When the tool isn't connected to the site, it says so, and succeeds.

## Using the connection

The commands that act on the site send requests to its MCP server, `<site>/mcp`: JSON-RPC requests, each in a `POST`,
with `Content-Type: application/json`, `Accept: application/json, text/event-stream`, and
`Authorization: Bearer <access token>`, whose response has to be JSON (see
[MCP server](https://github.com/parkingradio/website/blob/main/docs/design/server/mcp.md)). That header is only sent to
`<site>/mcp`. When the tool isn't connected to the site, these commands fail, and say to run `parkingradio auth login`.

A refresh replaces both tokens (see
[Connections](https://github.com/parkingradio/website/blob/main/docs/design/server/oauth.md#connections)), so:

- When the access token expires in less than a minute, the tool refreshes it before the request: it sends
  `grant_type` `refresh_token`, `refresh_token`, `client_id` and `resource` to `<site>/api/oauth/token`, and keeps the
  new tokens, which it then uses. The answer is checked like that of `auth login`.
- When the MCP server refuses the access token (401), the tool looks again at the tokens it keeps: when they've changed
  since, e.g. because another `parkingradio` refreshed them, it sends the request again with the new access token, and
  otherwise, it refreshes the tokens and then does. When it's refused again, the connection has ended.

Refreshes are done one at a time, with the lock (see [Credentials](README.md#conventions)), and each one first reads the
tokens again, so that another `parkingradio` that already refreshed them isn't undone.

When a refresh fails with `invalid_grant`, or a request is refused after a refresh, the connection has ended, e.g. the
admin disconnected it, or it went unused for 90 days: the command fails, and says to run `parkingradio auth login`.
When the site can't be reached, the command fails, and says so: if that was during a refresh, the connection may have
ended. Either way, the tool keeps the tokens it has.
