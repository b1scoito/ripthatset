# Using Proxies with RipThatSet

## Why Proxies Are Essential

RipThatSet makes multiple requests to the Shazam API for each segment of audio. The Shazam API has strict rate limiting that can significantly impact performance:

- Without a proxy, you might hit rate limits after ~20 requests
- Rate limits can cause long delays (10+ minutes)
- Single IP addresses may get temporarily blocked
- Processing speed becomes extremely slow

## Recommended Solution: Rotating Proxies

We strongly recommend using a rotating proxy service like OxyLabs for optimal performance:

### Benefits
- Distribute requests across multiple IPs
- Avoid rate limit restrictions
- Maintain high processing speed
- Get more reliable results
- No need to manage multiple proxy lists

### Recommended Providers
1. OxyLabs (Recommended)
   - Large IP pool
   - Fast rotation
   - Reliable service
   - Good geographic distribution

2. Other options:
   - Bright Data
   - IPRoyal
   - Smartproxy

## Usage with OxyLabs

```bash
poetry run ripthatset your_file.mp3 --proxy "http://customer:pass@pr.oxylabs.io:7777"
```

### Configuration Tips
- Use HTTPS proxies when possible
- Ensure high rotation frequency
- Use proxies from diverse locations
- Monitor proxy performance with --verbose flag

## Performance Comparison

Testing with a 1-hour audio file:

```
Without Proxy:
- Processing time: 2+ hours
- Success rate: ~60%
- Frequent timeouts

With Rotating Proxy:
- Processing time: 15-20 minutes
- Success rate: 90%+
- Consistent performance
```

## Troubleshooting

Common proxy-related issues:

1. 407 Errors
   - Check credentials
   - Verify proxy URL format
   - Ensure proxy service is active

2. Slow Performance
   - Check proxy rotation frequency
   - Verify IP pool size
   - Consider geographic location of proxies

3. Connection Errors
   - Check network connectivity
   - Verify proxy service status
   - Try different proxy endpoints
