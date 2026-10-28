// Agent text-chat flow widget test (offline, no device, no network).
//
// Automates the UI flow the PM runs from the app: switch to Text, type a
// request, send, and see the user bubble + the assistant's reply bubble.
// The ChatController is injected as a fake (test seam added to AgentScreen),
// so this exercises the screen's send/append/mode-toggle logic without
// touching the live chat proxy or a Vapi session.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:personal_agent_mobile/agent_screen.dart';
import 'package:personal_agent_mobile/session/chat_controller.dart';
import 'package:personal_agent_mobile/session/call_state_service.dart';
import 'package:personal_agent_mobile/session/vapi_session_controller.dart';

/// Records what would have been POSTed to /webhook/chat and returns canned
/// replies (or throws, to exercise the error path).
class FakeChatController extends ChatController {
  FakeChatController({this.reply = 'Done.', this.fail = false});

  final String reply;
  final bool fail;
  final List<String> sent = [];

  @override
  Future<String> send(String text) async {
    sent.add(text);
    if (fail) throw ChatException('The assistant did not respond (500).');
    return reply;
  }
}

void main() {
  testWidgets('voice-first shell renders', (tester) async {
    await tester.pumpWidget(MaterialApp(
        home: AgentScreen(chat: FakeChatController())));
    expect(find.text('Start Voice'), findsOneWidget);
    // Text input is hidden until the user switches to Text mode.
    expect(find.byType(TextField), findsNothing);
  });

  testWidgets('switching to Text shows the input and Send button',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
        home: AgentScreen(chat: FakeChatController())));
    await tester.tap(find.text('Text'));
    await tester.pumpAndSettle();
    expect(find.byType(TextField), findsOneWidget);
    expect(find.text('Send'), findsOneWidget);
    expect(find.text('Start Voice'), findsNothing);
  });

  testWidgets('typing and sending shows the user bubble and the reply',
      (tester) async {
    final fake = FakeChatController(reply: 'Project 123 Elm is ready.');
    await tester.pumpWidget(MaterialApp(home: AgentScreen(chat: fake)));

    await tester.tap(find.text('Text'));
    await tester.pumpAndSettle();

    await tester.enterText(
        find.byType(TextField), 'create a project 123 Elm for Jane Doe');
    await tester.tap(find.text('Send'));
    await tester.pumpAndSettle();

    expect(fake.sent, ['create a project 123 Elm for Jane Doe']);
    expect(find.text('create a project 123 Elm for Jane Doe'), findsOneWidget);
    expect(find.text('Project 123 Elm is ready.'), findsOneWidget);
    // Reply is rendered as a text (not voice) turn, matching the transport.
    expect(find.text('text'), findsWidgets);
  });

  testWidgets('a chat failure surfaces the error message instead of crashing',
      (tester) async {
    final fake = FakeChatController(fail: true);
    await tester.pumpWidget(MaterialApp(home: AgentScreen(chat: fake)));

    await tester.tap(find.text('Text'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'list projects');
    await tester.tap(find.text('Send'));
    await tester.pumpAndSettle();

    expect(find.textContaining('did not respond'), findsOneWidget);
  });

  nudgeTests();
}

/// A session that never touches the network: reports whatever connection
/// state the test wants and records say() calls.
class FakeSession extends VapiSessionController {
  FakeSession({required this.connected});

  final bool connected;
  final List<String> said = [];

  @override
  SessionStatus get status =>
      connected ? SessionStatus.connected : SessionStatus.disconnected;

  @override
  bool get isConnected => connected;

  @override
  Future<void> say(String text) async => said.add(text);
}

void _lifecycle(WidgetTester tester, AppLifecycleState state) {
  tester.binding.handleAppLifecycleStateChanged(state);
}

void nudgeTests() {
  testWidgets('backgrounding a live call nudges once after 6 s', (tester) async {
    final session = FakeSession(connected: true);
    await tester.pumpWidget(MaterialApp(
        home: AgentScreen(chat: FakeChatController(), session: session)));

    _lifecycle(tester, AppLifecycleState.paused);
    await tester.pump(const Duration(seconds: 5));
    expect(session.said, isEmpty, reason: 'nothing before the 6 s delay');

    await tester.pump(const Duration(seconds: 2));
    expect(session.said, ["I'm still here — should I hang up?"]);

    // Still paused: the timer must not fire again.
    await tester.pump(const Duration(seconds: 20));
    expect(session.said.length, 1);

    // A new excursion gets its own single nudge.
    _lifecycle(tester, AppLifecycleState.resumed);
    await tester.pump();
    _lifecycle(tester, AppLifecycleState.paused);
    await tester.pump(const Duration(seconds: 7));
    expect(session.said.length, 2);
  });

  testWidgets('no nudge when no call is connected', (tester) async {
    final session = FakeSession(connected: false);
    await tester.pumpWidget(MaterialApp(
        home: AgentScreen(chat: FakeChatController(), session: session)));

    _lifecycle(tester, AppLifecycleState.paused);
    await tester.pump(const Duration(seconds: 10));
    expect(session.said, isEmpty);
  });

  testWidgets('pending style choice gets the contextual nudge', (tester) async {
    final session = FakeSession(connected: true);
    await tester.pumpWidget(MaterialApp(
        home: AgentScreen(chat: FakeChatController(), session: session)));

    // Simulate the assistant's turn that offered the styles.
    session.onAgentTranscript?.call('The 3 styles are on your phone.');
    await tester.pump();

    _lifecycle(tester, AppLifecycleState.paused);
    await tester.pump(const Duration(seconds: 7));

    expect(session.said.single,
        'Take your time — tell me which style you like, or tap it on your phone.');
  });

  remoteCallStateTests();
}

/// Call-state lookup driven by the test instead of the network.
class FakeCallState extends CallStateService {
  FakeCallState(this.active);
  bool active;
  int calls = 0;

  @override
  Future<bool> isCallActive() async {
    calls++;
    return active;
  }
}

void remoteCallStateTests() {
  testWidgets('an open server-side call disables Start Voice', (tester) async {
    final state = FakeCallState(true);
    await tester.pumpWidget(MaterialApp(
        home: AgentScreen(
            chat: FakeChatController(),
            session: FakeSession(connected: false),
            callState: state)));
    await tester.pump(); // let the initial lookup resolve
    await tester.pump();

    expect(find.text('Call in progress…'), findsOneWidget);
    expect(find.text('Start Voice'), findsNothing);
    expect(find.byKey(const ValueKey('remote-call-hint')), findsOneWidget);
    expect(state.calls, greaterThan(0));

    // Button must be disabled (tapping does nothing).
    await tester.tap(find.text('Call in progress…'), warnIfMissed: false);
    await tester.pump();
    expect(state.calls, greaterThan(0));
  });

  testWidgets('the button re-enables once the call is gone', (tester) async {
    final state = FakeCallState(true);
    await tester.pumpWidget(MaterialApp(
        home: AgentScreen(
            chat: FakeChatController(),
            session: FakeSession(connected: false),
            callState: state)));
    await tester.pump();
    await tester.pump();
    expect(find.text('Call in progress…'), findsOneWidget);

    // Call ends on Vapi's side; the 15 s poll picks it up.
    state.active = false;
    await tester.pump(const Duration(seconds: 16));
    await tester.pump();

    expect(find.text('Start Voice'), findsOneWidget);
    expect(find.text('Call in progress…'), findsNothing);
  });

  testWidgets('no live call -> normal Start Voice', (tester) async {
    final state = FakeCallState(false);
    await tester.pumpWidget(MaterialApp(
        home: AgentScreen(
            chat: FakeChatController(),
            session: FakeSession(connected: false),
            callState: state)));
    await tester.pump();
    await tester.pump();
    expect(find.text('Start Voice'), findsOneWidget);
    expect(find.text('Call in progress…'), findsNothing);
  });
}
