# The Study — member sign-in

Canonical URL: https://art.alieninc.tech/accounts/

Supabase email + password, with an email magic-link fallback. Accounts are
admin-provisioned (`shouldCreateUser: false`); the old `accounts.html` magic-link
page is a redirect to this folder. Supabase Auth Site URL must stay set to the
canonical URL above. Old `accounts.thedailyartcult.lol` host is dead.
