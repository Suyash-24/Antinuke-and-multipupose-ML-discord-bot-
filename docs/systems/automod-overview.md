# AutoMod

AutoMod in Aegis is meant to be configurable and practical rather than overloaded.

## Built-in protections

- invite filtering
- referral-link filtering
- known copypasta detection
- `@everyone` and `@here` abuse checks
- max mention limits
- max role mention limits
- max line limits
- duplicate-message spam detection
- custom filters
- redirect-link resolution
- nickname dehoisting

## Custom filters

Filters are useful when your community has server-specific abuse patterns that generic rules will miss.

You can define:

- quotes
- glob-like patterns
- regex patterns

## Integration with strikes

AutoMod can delete only, assign strikes, or trigger a configured punishment threshold depending on your setup.

## Related commands

- `^automod`
- `^automod antiinvite`
- `^automod antireferral`
- `^automod anticopypasta`
- `^automod antiduplicate`
- `^automod filter add`
- `^punishment`
