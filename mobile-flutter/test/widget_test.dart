// Smoke test for the Agent screen shell.
//
// Pumps AgentScreen with an injected fake ChatController without starting a
// Vapi call (which would require a real WebRTC device + assistant), so no
// native plugin channel is touched. The app ROOT (auth gate) needs platform
// plugins and is exercised on-device, not here.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:personal_agent_mobile/agent_screen.dart';
import 'package:personal_agent_mobile/session/chat_controller.dart';

class _SilentChat extends ChatController {
  @override
  Future<String> send(String text) async => '';
}

void main() {
  testWidgets('Agent screen renders the voice/text mode switch', (tester) async {
    await tester.pumpWidget(MaterialApp(home: AgentScreen(chat: _SilentChat())));

    // Voice-first UI (ADR-8): the mode switch and the voice CTA are present.
    expect(find.text('Voice'), findsOneWidget);
    expect(find.text('Text'), findsOneWidget);
    expect(find.text('Start Voice'), findsOneWidget);
  });
}
