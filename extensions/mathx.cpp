// Extension spike: a C++ function with the Anvil extension ABI.
// Every extension entry point takes doubles and returns a double.

extern "C" __declspec(dllexport) double anvil_ext_gcd(double a, double b) {
  long x = (long)a;
  long y = (long)b;
  if (x < 0) x = -x;
  if (y < 0) y = -y;
  while (y != 0) {
    long t = x % y;
    x = y;
    y = t;
  }
  return (double)x;
}

extern "C" __declspec(dllexport) double anvil_ext_lcm(double a, double b) {
  long x = (long)a;
  long y = (long)b;
  if (x == 0 || y == 0) return 0.0;
  double g = anvil_ext_gcd(a, b);
  return (double)(x / (long)g * y);
}
