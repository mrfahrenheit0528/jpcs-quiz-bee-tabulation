// Windows 10+ native mDNS/DNS-SD. No Bonjour or Python installation required.
using System;
using System.Net;
using System.Runtime.InteropServices;
using System.Threading;

public sealed class QuizDnsSd : IDisposable {
    [UnmanagedFunctionPointer(CallingConvention.Winapi)]
    private delegate void Completion(uint status, IntPtr context, IntPtr instance);
    [StructLayout(LayoutKind.Sequential)]
    private struct RegisterRequest {
        public uint Version, InterfaceIndex;
        public IntPtr Instance, Callback, Context, Credentials;
        [MarshalAs(UnmanagedType.Bool)] public bool Unicast;
    }
    [DllImport("dnsapi.dll", CharSet=CharSet.Unicode)]
    private static extern IntPtr DnsServiceConstructInstance(string service, string host, ref uint ipv4,
        IntPtr ipv6, ushort port, ushort priority, ushort weight, uint count, IntPtr keys, IntPtr values);
    [DllImport("dnsapi.dll")] private static extern uint DnsServiceRegister(IntPtr request, IntPtr cancel);
    [DllImport("dnsapi.dll")] private static extern uint DnsServiceRegisterCancel(IntPtr cancel);
    [DllImport("dnsapi.dll")] private static extern uint DnsServiceDeRegister(IntPtr request, IntPtr cancel);
    [DllImport("dnsapi.dll")] private static extern void DnsServiceFreeInstance(IntPtr instance);
    private readonly ManualResetEvent completed = new ManualResetEvent(false);
    private readonly Completion callback;
    private IntPtr instance, resultInstance, request, cancel;
    private bool registered, disposed;
    private uint result;
    public string RegisteredHost { get; private set; }

    public QuizDnsSd(string hostname, string ipv4, ushort port, uint interfaceIndex) {
        callback = OnComplete; // Root the delegate for the entire native operation.
        uint address = BitConverter.ToUInt32(IPAddress.Parse(ipv4).GetAddressBytes(), 0);
        instance = DnsServiceConstructInstance("JPCS Quiz ("+hostname+")._http._tcp.local", hostname,
            ref address, IntPtr.Zero, port, 0, 0, 0, IntPtr.Zero, IntPtr.Zero);
        if (instance == IntPtr.Zero) throw new InvalidOperationException("DnsServiceConstructInstance failed.");
        var data = new RegisterRequest {Version=1, InterfaceIndex=interfaceIndex, Instance=instance,
            Callback=Marshal.GetFunctionPointerForDelegate(callback), Unicast=false};
        request=Marshal.AllocHGlobal(Marshal.SizeOf(typeof(RegisterRequest)));
        Marshal.StructureToPtr(data,request,false);
        cancel=Marshal.AllocHGlobal(IntPtr.Size); Marshal.WriteIntPtr(cancel,IntPtr.Zero);
        uint status=DnsServiceRegister(request,cancel);
        if(status != 9506) { Dispose(); throw new InvalidOperationException("DnsServiceRegister error "+status); }
        // Native registration is asynchronous. Keep request and callback alive until completion.
        if(!completed.WaitOne(TimeSpan.FromSeconds(20))) {
            DnsServiceRegisterCancel(cancel);
            completed.WaitOne(); // Keep native memory alive until cancellation callback.
            if(result==0) registered=true;
            Dispose(); throw new TimeoutException("DNS-SD registration timed out and was cancelled.");
        }
        if(result != 0) { uint code=result; Dispose(); throw new InvalidOperationException("DNS-SD collision or registration error "+code); }
        registered=true;
        if(!String.Equals((RegisteredHost ?? "").TrimEnd('.'), hostname.TrimEnd('.'), StringComparison.OrdinalIgnoreCase)) {
            Dispose(); throw new InvalidOperationException("Hostname collision: Windows renamed the host to "+RegisteredHost);
        }
    }
    private void OnComplete(uint status, IntPtr context, IntPtr response) {
        result=status;
        if(resultInstance != IntPtr.Zero && resultInstance != instance && resultInstance != response) DnsServiceFreeInstance(resultInstance);
        resultInstance=response;
        if(response != IntPtr.Zero) {
            IntPtr host=Marshal.ReadIntPtr(response,IntPtr.Size);
            RegisteredHost=Marshal.PtrToStringUni(host);
        }
        completed.Set();
    }
    public void Dispose() {
        if(disposed) return;
        if(registered) {
            completed.Reset();
            uint status=DnsServiceDeRegister(request,IntPtr.Zero);
            if(status==9506) completed.WaitOne(); // Stop command kills a stuck companion; process exit withdraws registration.
            registered=false;
        }
        if(resultInstance != IntPtr.Zero && resultInstance != instance) DnsServiceFreeInstance(resultInstance);
        if(instance != IntPtr.Zero) DnsServiceFreeInstance(instance);
        if(request != IntPtr.Zero) Marshal.FreeHGlobal(request);
        if(cancel != IntPtr.Zero) Marshal.FreeHGlobal(cancel);
        resultInstance=instance=request=cancel=IntPtr.Zero;
        disposed=true; completed.Dispose();
        GC.KeepAlive(callback);
    }
}
