/**
 * Formats an ISO 8601 duration string into a human-readable format.
 * Examples: 
 * "P30D" -> "30 Days"
 * "P1Y" -> "1 Year"
 * "P1Y2M" -> "1 Year, 2 Months"
 * "PT1H" -> "1 Hour"
 */
export function formatIsoDuration(duration: string): string {
    if (!duration) return "";

    // Regex to capture the various parts of the ISO 8601 duration
    // P(n)Y(n)M(n)W(n)DT(n)H(n)M(n)S
    const regex = /P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?/;
    const matches = duration.match(regex);

    if (!matches) return duration;

    const [
        _,
        years,
        months,
        weeks,
        days,
        hours,
        minutes,
        seconds
    ] = matches;

    const parts: string[] = [];

    if (years) parts.push(`${years} Year${parseInt(years) > 1 ? 's' : ''}`);
    if (months) parts.push(`${months} Month${parseInt(months) > 1 ? 's' : ''}`);
    if (weeks) parts.push(`${weeks} Week${parseInt(weeks) > 1 ? 's' : ''}`);
    if (days) parts.push(`${days} Day${parseInt(days) > 1 ? 's' : ''}`);
    if (hours) parts.push(`${hours} Hour${parseInt(hours) > 1 ? 's' : ''}`);
    if (minutes) parts.push(`${minutes} Minute${parseInt(minutes) > 1 ? 's' : ''}`);
    if (seconds) parts.push(`${seconds} Second${parseInt(seconds) > 1 ? 's' : ''}`);

    return parts.join(", ");
}

/**
 * Formats an ISO 3166-1 alpha-2 region code into a human-readable name.
 * Examples:
 * "US" -> "United States"
 * "DE" -> "Germany"
 */
export function formatRegionName(code: string): string {
    try {
        const regionNames = new Intl.DisplayNames(['en'], { type: 'region' });
        return regionNames.of(code) || code;
    } catch (e) {
        return code;
    }
}
