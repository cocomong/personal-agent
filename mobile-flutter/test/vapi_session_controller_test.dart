// Voice start single-flight tests (offline; the Vapi SDK client and the n8n
// call-start hook are fakes injected through the controller's test seams).
//
// Regression tests for the double-tap bug found on a slow phone: two rapid
// taps on the talk button during the connecting window created two concurrent
// Vapi calls — two assistants talking over each other — because start() had
// no in-flight guard and the second attempt's opening stop() was a no-op
// (its _call wasn't assigned yet).

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vapi/vapi.dart';
// VapiCallMonitor / VapiCallTransport are part of the VapiCall interface but
// are not re-exported by package:vapi/vapi.dart (SDK 0.1.0 packaging gap), so
// the fake reaches the package's shared lib for them.
// ignore: implementation_imports
import 'package:vapi/src/shared/vapi_call_monitor.dart';
// ignore: implementation_imports
import 'package:vapi/src/shared/vapi_call_transport.dart';

import 'package:personal_agent_mobile/agent_screen.dart';
import 'package:personal_agent_mobile/session/chat_controller.dart';
import 'package:personal_agent_mobile/session/vapi_session_controller.dart';

/// Fake SDK client: start() parks on a completer so tests control exactly
/// when the connecting window closes, and records every attempt.
class FakeVapiClient implements VapiClientInterface {
  final startCompleters = <Completer<VapiCall>>[];

  @override
  Future<VapiCall> start({
    String? assistantId,
    Map<String, dynamic>? assistant,
    Map<String, dynamic> assistantOverrides = const {},
    Duration clientCreationTimeoutDuration = const Duration(seconds: 10),
    bool waitUntilActive = false,
  }) {
    final completer = Completer<VapiCall>();
    startCompleters.add(completer);
    return completer.future;
  }

  /// Resolves the n-th pending start() attempt with a fresh fake call.
  FakeVapiCall completeStart(int n) {
    final call = FakeVapiCall('call-$n');
    startCompleters[n].complete(call);
    return call;
  }

  /// Fails the n-th pending start() attempt.
  void failStart(int n, Object error) => startCompleters[n].completeError(error);

  @override
  void dispose() {}

  @override
  String get publicKey => 'test-public-key';

  @override
  String get apiBaseUrl => 'https://api.vapi.ai';
}

/// Fake call implementing the full VapiCall interface; only the
/// stop/dispose counters and the event stream are functional.
class FakeVapiCall implements VapiCall {
  FakeVapiCall(this.id);

  @override
  final String id;

  int stopCount = 0;
  int disposeCount = 0;
  final _events = StreamController<VapiEvent>.broadcast();

  void emit(String label, [dynamic value]) => _events.add(VapiEvent(label, value));

  @override
  Future<void> stop() async {
    stopCount++;
  }

  @override
  void dispose() {
    disposeCount++;
    unawaited(_events.close());
  }

  @override
  Stream<VapiEvent> get onEvent => _events.stream;

  @override
  Future<void> send(Map<String, dynamic> message) async {}

  // -- boilerplate metadata --
  @override
  String get assistantId => 'assistant';
  @override
  Map<String, dynamic> get assistantOverrides => const {};
  @override
  String get orgId => 'org';
  @override
  DateTime get createdAt => DateTime(2026);
  @override
  DateTime get updatedAt => DateTime(2026);
  @override
  VapiCallStatus get status => VapiCallStatus.active;
  @override
  String get type => 'webCall';
  @override
  VapiCallMonitor get monitor => const VapiCallMonitor(
      listenUrl: 'wss://example.listen', controlUrl: 'https://example.control');
  @override
  VapiCallTransport get transport => const VapiCallTransport(
      provider: 'daily', assistantVideoEnabled: false, callUrl: 'https://example.call');
  @override
  String get webCallUrl => 'https://example.webcall';
  @override
  bool get isMuted => false;
  @override
  void setMuted(bool muted) {}
  @override
  void setAudioDevice({VapiAudioDevice? device}) {}
}

class _SilentChat extends ChatController {
  @override
  Future<String> send(String text) async => '';
}

VapiSessionController _controller(FakeVapiClient client) =>
    VapiSessionController(
      clientFactory: () => client,
      overridesFetcher: () async => <String, dynamic>{},
    );

/// Pumps pending microtasks so an un-awaited start() reaches the parked
/// `_client.start()` boundary (the fake hook fetch has no timers).
Future<void> _park() => Future<void>.delayed(Duration.zero);

void main() {
  test('double-tap during the connecting window starts exactly ONE call',
      () async {
    final client = FakeVapiClient();
    final controller = _controller(client);

    final first = controller.start(); // tap 1 — still connecting…
    await _park();
    final second = controller.start(); // tap 2, moments later
    final third = controller.start(); // and a frantic tap 3

    final call = client.completeStart(0); // the call finally comes up
    await Future.wait([first, second, third]);

    expect(client.startCompleters, hasLength(1)); // ONE SDK start, not three
    expect(call.stopCount, 0); // …and it stayed up
    expect(controller.status, SessionStatus.connecting); // pre call-start

    call.emit('call-start');
    await _park();
    expect(controller.status, SessionStatus.connected);
  });

  test('flipping to Text mid-connect supersedes the start: torn down, not orphaned',
      () async {
    final client = FakeVapiClient();
    final controller = _controller(client);

    final starting = controller.start();
    await _park();

    await controller.stop(); // mode switch to Text while still connecting
    expect(controller.status, SessionStatus.disconnected);

    final late = client.completeStart(0); // SDK start resolves AFTER the stop
    await starting;

    expect(late.stopCount, 1); // the late call was torn down…
    expect(late.disposeCount, 1); // …and disposed, never orphaned
    expect(controller.status, SessionStatus.disconnected);
  });

  test('a failed start rolls back to disconnected and releases the guard',
      () async {
    final client = FakeVapiClient();
    final controller = _controller(client);

    final first = controller.start();
    await _park();
    client.failStart(0, Exception('WebRTC negotiation failed'));
    Object? caught;
    try {
      await first;
    } catch (e) {
      caught = e;
    }
    expect(caught, isNotNull);
    expect(controller.status, SessionStatus.disconnected);

    // The guard is released: a fresh start goes through.
    final second = controller.start();
    await _park();
    final call = client.completeStart(1);
    await second;
    expect(client.startCompleters, hasLength(2));
    call.emit('call-start');
    await _park();
    expect(controller.status, SessionStatus.connected);
    await controller.stop();
  });

  testWidgets('talk button disables and shows Connecting… while the call comes up',
      (tester) async {
    final client = FakeVapiClient();
    final controller = _controller(client);

    await tester.pumpWidget(MaterialApp(
        home: AgentScreen(session: controller, chat: _SilentChat())));
    expect(find.text('Start Voice'), findsOneWidget);

    await tester.tap(find.text('Start Voice'));
    await tester.pump(); // status -> connecting, button rebuilds
    await tester.pump();

    final button = tester.widget<FilledButton>(find.byType(FilledButton).first);
    expect(button.onPressed, isNull); // disabled: a second tap is impossible
    expect(find.text('Connecting…'), findsOneWidget);
    expect(find.text('Start Voice'), findsNothing);

    // Wind down without leaving the parked start dangling.
    await controller.stop();
    client.completeStart(0); // late resolution; superseded -> disposed
    await tester.pumpAndSettle();
  });
}
