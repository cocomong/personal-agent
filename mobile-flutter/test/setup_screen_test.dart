import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:personal_agent_mobile/auth/setup_screen.dart';

void main() {
  testWidgets('setup screen explains the required address and starts setup',
      (tester) async {
    var started = 0;
    var signedOut = 0;
    var refreshed = 0;

    await tester.pumpWidget(MaterialApp(
      home: SetupScreen(
        onStartSetup: () => started++,
        onSignOut: () => signedOut++,
        onRefresh: () => refreshed++,
      ),
    ));

    expect(find.text('Set up your company'), findsOneWidget);
    expect(find.textContaining('Business address - required'), findsOneWidget);

    // The screen is a tall scroll view; bring each control into view first.
    await tester.ensureVisible(find.text('Start setup'));
    await tester.tap(find.text('Start setup'));
    await tester.pumpAndSettle();
    expect(started, 1);

    await tester.ensureVisible(find.text('Sign out'));
    await tester.tap(find.text('Sign out'));
    await tester.pumpAndSettle();
    expect(signedOut, 1);

    await tester.ensureVisible(find.textContaining('Already finished setting up'));
    await tester.tap(find.textContaining('Already finished setting up'));
    await tester.pumpAndSettle();
    expect(refreshed, 1);
  });

  testWidgets('refresh shows a spinner and an inline error', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: SetupScreen(
        onStartSetup: () {},
        onSignOut: () {},
        onRefresh: () {},
        refreshing: true,
        error: 'Could not reach the server.',
      ),
    ));

    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.text('Could not reach the server.'), findsOneWidget);
  });
}
