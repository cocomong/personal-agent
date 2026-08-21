// Smoke test for the Personal Agent app shell.
//
// Pumps the root widget without starting a Vapi call (which would require a
// real WebRTC device + assistant), so no native plugin channel is touched.

import 'package:flutter_test/flutter_test.dart';

import 'package:personal_agent_mobile/main.dart';

void main() {
  testWidgets('Agent screen renders the voice/text mode switch', (tester) async {
    await tester.pumpWidget(const PersonalAgentApp());

    // Voice-first UI (ADR-8): the mode switch and the voice CTA are present.
    expect(find.text('Voice'), findsOneWidget);
    expect(find.text('Text'), findsOneWidget);
    expect(find.text('Start Voice'), findsOneWidget);
  });
}
