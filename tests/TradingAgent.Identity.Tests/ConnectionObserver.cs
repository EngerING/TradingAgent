using System.Collections.Concurrent;
using System.Diagnostics.Tracing;

namespace TradingAgent.Identity.Tests;

internal sealed class ConnectionObserver : EventListener
{
    internal ConcurrentQueue<string> Addresses { get; } = new();
    protected override void OnEventSourceCreated(EventSource eventSource)
    {
        if (eventSource.Name == "System.Net.Sockets") EnableEvents(eventSource, EventLevel.Informational);
    }
    protected override void OnEventWritten(EventWrittenEventArgs eventData)
    {
        if (eventData.EventName == "ConnectStart" && eventData.Payload is { Count: > 0 }) Addresses.Enqueue(eventData.Payload[0]?.ToString() ?? "UNKNOWN");
    }
}
