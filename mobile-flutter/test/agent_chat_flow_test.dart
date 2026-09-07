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
}
