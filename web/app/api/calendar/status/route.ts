export const runtime = 'nodejs';

export async function POST(req: Request) {
    let body: any = {};
    try {
        body = await req.json();
    } catch { }
    const userId = body?.userId || '';
    const connectionRequestId = body?.connectionRequestId || '';

    const serverBase = process.env.PY_SERVER_URL || 'http://server:8000';
    const url = `${serverBase.replace(/\/$/, '')}/api/v1/calendar/status`;

    try {
        const resp = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
            body: JSON.stringify({ user_id: userId, connection_request_id: connectionRequestId }),
        });
        const data = await resp.json().catch(() => ({}));
        return new Response(JSON.stringify(data), {
            status: resp.status,
            headers: { 'Content-Type': 'application/json; charset=utf-8' },
        });
    } catch (e: any) {
        return new Response(
            JSON.stringify({ ok: false, error: 'Upstream error', detail: e?.message || String(e) }),
            { status: 502, headers: { 'Content-Type': 'application/json; charset=utf-8' } }
        );
    }
}
