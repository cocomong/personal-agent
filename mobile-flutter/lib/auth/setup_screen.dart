import 'package:flutter/material.dart';

/// Shown when a signed-in user has no company yet (`setup_complete == false`).
///
/// The setup itself is the voice conversation the assistant already runs
/// (firstMessage "let's get you set up" + the onboarding_steps prompt section),
/// so this screen's job is to introduce it and get out of the way. The app must
/// never drop a brand-new user straight into the assistant: before setup, the
/// assistant has no company to work on.
class SetupScreen extends StatelessWidget {
  const SetupScreen({
    super.key,
    required this.onStartSetup,
    required this.onSignOut,
    required this.onRefresh,
    this.refreshing = false,
    this.error,
  });

  final VoidCallback onStartSetup;
  final VoidCallback onSignOut;

  /// Re-checks /webhook/auth/me. Used when the user finished setup in a call
  /// or on another device and the cached flag is stale.
  final VoidCallback onRefresh;
  final bool refreshing;
  final String? error;

  static const _bg = Color(0xFF0F172A);
  static const _card = Color(0xFF17233B);
  static const _blue = Color(0xFF2563EB);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _bg,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 32),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 460),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Icon(Icons.business_outlined, size: 52, color: _blue),
                  const SizedBox(height: 20),
                  const Text(
                    'Set up your company',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 26,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 12),
                  const Text(
                    'One short conversation and your workspace is ready. '
                    'The assistant will ask a few questions, then it can handle '
                    'projects, invoices, payments and payroll for you.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Color(0xFF94A3B8), fontSize: 15, height: 1.45),
                  ),
                  const SizedBox(height: 28),
                  Container(
                    padding: const EdgeInsets.all(18),
                    decoration: BoxDecoration(
                      color: _card,
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: const Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _SetupItem('Company name'),
                        _SetupItem('Your name and how you want to be addressed'),
                        _SetupItem(
                          'Business address - required: it appears on every invoice',
                        ),
                        _SetupItem('GST number (PST optional)'),
                        _SetupItem('How customers should pay'),
                        _SetupItem('Your crew: names, trades, hourly rates'),
                      ],
                    ),
                  ),
                  const SizedBox(height: 28),
                  SizedBox(
                    height: 52,
                    child: ElevatedButton.icon(
                      onPressed: onStartSetup,
                      icon: const Icon(Icons.mic_none),
                      label: const Text(
                        'Start setup',
                        style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                      ),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: _blue,
                        foregroundColor: Colors.white,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    'Takes about a minute. Speak normally - you can interrupt.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.white.withValues(alpha: 0.45), fontSize: 12.5),
                  ),
                  if (error != null) ...[
                    const SizedBox(height: 14),
                    Text(
                      error!,
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: Color(0xFFF87171), fontSize: 13),
                    ),
                  ],
                  const SizedBox(height: 18),
                  TextButton(
                    onPressed: refreshing ? null : onRefresh,
                    child: refreshing
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2, color: _blue),
                          )
                        : const Text(
                            'Already finished setting up? Refresh',
                            style: TextStyle(color: Color(0xFF94A3B8), fontSize: 13.5),
                          ),
                  ),
                  TextButton(
                    onPressed: onSignOut,
                    child: const Text(
                      'Sign out',
                      style: TextStyle(color: Color(0xFF64748B), fontSize: 13),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _SetupItem extends StatelessWidget {
  const _SetupItem(this.text);
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.only(top: 2),
            child: Icon(Icons.check_circle_outline, size: 17, color: Color(0xFF38BDF8)),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              text,
              style: const TextStyle(color: Color(0xFFE2E8F0), fontSize: 14, height: 1.35),
            ),
          ),
        ],
      ),
    );
  }
}
