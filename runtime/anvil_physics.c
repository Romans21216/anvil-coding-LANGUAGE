#include "anvil_runtime.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

enum { ANVIL_PHYSICS_BODIES = 128, ANVIL_PHYSICS_SOLVER_ITERATIONS = 4 };
enum { ANVIL_PHYSICS_CIRCLE, ANVIL_PHYSICS_BOX };
#define ANVIL_PHYSICS_MAX_COORDINATE 1000000000.0
#define ANVIL_PHYSICS_MAX_RADIUS 1000000.0
#define ANVIL_PHYSICS_MAX_SPEED 1000000.0

typedef struct {
  double x, y, vx, vy, force_x, force_y;
  double radius, half_width, half_height, mass, restitution, friction;
  uint32_t generation;
  int active, shape;
} AnvilPhysicsBody;

static AnvilPhysicsBody anvil_physics_bodies[ANVIL_PHYSICS_BODIES];
static int anvil_physics_active_capacity = ANVIL_PHYSICS_BODIES;
static double anvil_physics_gravity_x;
static double anvil_physics_gravity_y = -9.81;

static AnvilPhysicsBody *anvil_physics_body(double handle, int *slot_out) {
  const double max_handle = (double)UINT32_MAX * ANVIL_PHYSICS_BODIES +
                            (ANVIL_PHYSICS_BODIES - 1);
  if (!isfinite(handle) || handle < 0.0 || handle > max_handle ||
      floor(handle) != handle)
    return NULL;
  uint64_t encoded = (uint64_t)handle;
  int slot = (int)(encoded % ANVIL_PHYSICS_BODIES);
  uint32_t generation = (uint32_t)(encoded / ANVIL_PHYSICS_BODIES);
  AnvilPhysicsBody *body = &anvil_physics_bodies[slot];
  if (!generation || !body->active || body->generation != generation)
    return NULL;
  if (slot_out)
    *slot_out = slot;
  return body;
}

static double anvil_physics_allocate_body(double x, double y, double radius,
                                          double half_width,
                                          double half_height, double mass,
                                          int shape) {
  for (int slot = 0; slot < anvil_physics_active_capacity; ++slot) {
    AnvilPhysicsBody *body = &anvil_physics_bodies[slot];
    if (body->active)
      continue;
    uint32_t generation = body->generation + 1;
    if (!generation)
      generation = 1;
    memset(body, 0, sizeof(*body));
    body->generation = generation;
    body->active = 1;
    body->shape = shape;
    body->x = x;
    body->y = y;
    body->radius = radius;
    body->half_width = half_width;
    body->half_height = half_height;
    body->mass = mass;
    body->friction = 0.5;
    return (double)generation * ANVIL_PHYSICS_BODIES + slot;
  }
  return -1.0;
}

double anvil_body_create(double x, double y, double radius, double mass) {
  if (!isfinite(x) || !isfinite(y) || !isfinite(radius) || !isfinite(mass) ||
      fabs(x) > ANVIL_PHYSICS_MAX_COORDINATE ||
      fabs(y) > ANVIL_PHYSICS_MAX_COORDINATE || radius < 1.0e-6 ||
      radius > ANVIL_PHYSICS_MAX_RADIUS || mass < 0.0 || mass > 1.0e12 ||
      (mass > 0.0 && mass < 1.0e-6))
    return -1.0;
  return anvil_physics_allocate_body(x, y, radius, 0.0, 0.0, mass,
                                     ANVIL_PHYSICS_CIRCLE);
}

double anvil_body_create_box(double x, double y, double width, double height,
                             double mass) {
  if (!isfinite(x) || !isfinite(y) || !isfinite(width) || !isfinite(height) ||
      !isfinite(mass) || fabs(x) > ANVIL_PHYSICS_MAX_COORDINATE ||
      fabs(y) > ANVIL_PHYSICS_MAX_COORDINATE || width < 2.0e-6 ||
      width > 2.0 * ANVIL_PHYSICS_MAX_RADIUS || height < 2.0e-6 ||
      height > 2.0 * ANVIL_PHYSICS_MAX_RADIUS || mass < 0.0 || mass > 1.0e12 ||
      (mass > 0.0 && mass < 1.0e-6))
    return -1.0;
  return anvil_physics_allocate_body(x, y, 0.0, width * 0.5, height * 0.5,
                                     mass, ANVIL_PHYSICS_BOX);
}

double anvil_physics_capacity(double requested_capacity) {
  if (!isfinite(requested_capacity) || floor(requested_capacity) != requested_capacity ||
      requested_capacity < 1.0 || requested_capacity > ANVIL_PHYSICS_BODIES)
    return -1.0;
  int capacity = (int)requested_capacity;
  for (int slot = capacity; slot < anvil_physics_active_capacity; ++slot) {
    if (anvil_physics_bodies[slot].active)
      return -1.0;
  }
  anvil_physics_active_capacity = capacity;
  return (double)anvil_physics_active_capacity;
}

double anvil_body_destroy(double handle) {
  AnvilPhysicsBody *body = anvil_physics_body(handle, NULL);
  if (!body)
    return 0.0;
  body->active = 0;
  body->force_x = 0.0;
  body->force_y = 0.0;
  return 1.0;
}

double anvil_body_active(double handle) {
  return anvil_physics_body(handle, NULL) ? 1.0 : 0.0;
}

double anvil_body_x(double handle) {
  AnvilPhysicsBody *body = anvil_physics_body(handle, NULL);
  return body ? body->x : -1.0;
}

double anvil_body_y(double handle) {
  AnvilPhysicsBody *body = anvil_physics_body(handle, NULL);
  return body ? body->y : -1.0;
}

double anvil_body_vx(double handle) {
  AnvilPhysicsBody *body = anvil_physics_body(handle, NULL);
  return body ? body->vx : -1.0;
}

double anvil_body_vy(double handle) {
  AnvilPhysicsBody *body = anvil_physics_body(handle, NULL);
  return body ? body->vy : -1.0;
}

double anvil_body_set_velocity(double handle, double vx, double vy) {
  AnvilPhysicsBody *body = anvil_physics_body(handle, NULL);
  if (!body || body->mass <= 0.0 || !isfinite(vx) || !isfinite(vy) ||
      fabs(vx) > ANVIL_PHYSICS_MAX_SPEED || fabs(vy) > ANVIL_PHYSICS_MAX_SPEED)
    return 0.0;
  body->vx = vx;
  body->vy = vy;
  return 1.0;
}

double anvil_body_force(double handle, double force_x, double force_y) {
  AnvilPhysicsBody *body = anvil_physics_body(handle, NULL);
  if (!body || body->mass <= 0.0 || !isfinite(force_x) || !isfinite(force_y) ||
      fabs(force_x) > 1.0e12 || fabs(force_y) > 1.0e12)
    return 0.0;
  double next_force_x = body->force_x + force_x;
  double next_force_y = body->force_y + force_y;
  if (!isfinite(next_force_x) || !isfinite(next_force_y) ||
      fabs(next_force_x) > 1.0e12 || fabs(next_force_y) > 1.0e12)
    return 0.0;
  body->force_x = next_force_x;
  body->force_y = next_force_y;
  return 1.0;
}

double anvil_body_restitution(double handle, double restitution) {
  AnvilPhysicsBody *body = anvil_physics_body(handle, NULL);
  if (!body || !isfinite(restitution) || restitution < 0.0 || restitution > 1.0)
    return 0.0;
  body->restitution = restitution;
  return 1.0;
}

double anvil_body_friction(double handle, double friction) {
  AnvilPhysicsBody *body = anvil_physics_body(handle, NULL);
  if (!body || !isfinite(friction) || friction < 0.0 || friction > 1.0)
    return 0.0;
  body->friction = friction;
  return 1.0;
}

static int anvil_physics_contact(const AnvilPhysicsBody *a,
                                 const AnvilPhysicsBody *b, double *normal_x,
                                 double *normal_y, double *penetration) {
  if (a->shape == ANVIL_PHYSICS_CIRCLE &&
      b->shape == ANVIL_PHYSICS_CIRCLE) {
    double dx = b->x - a->x, dy = b->y - a->y;
    double radius = a->radius + b->radius;
    double distance_sq = dx * dx + dy * dy;
    if (distance_sq >= radius * radius)
      return 0;
    double distance = sqrt(distance_sq);
    *normal_x = distance > 1.0e-12 ? dx / distance : 1.0;
    *normal_y = distance > 1.0e-12 ? dy / distance : 0.0;
    *penetration = radius - distance;
    return 1;
  }

  if (a->shape == ANVIL_PHYSICS_BOX && b->shape == ANVIL_PHYSICS_BOX) {
    double dx = b->x - a->x, dy = b->y - a->y;
    double overlap_x = a->half_width + b->half_width - fabs(dx);
    double overlap_y = a->half_height + b->half_height - fabs(dy);
    if (overlap_x <= 0.0 || overlap_y <= 0.0)
      return 0;
    if (overlap_x < overlap_y) {
      *normal_x = dx >= 0.0 ? 1.0 : -1.0;
      *normal_y = 0.0;
      *penetration = overlap_x;
    } else {
      *normal_x = 0.0;
      *normal_y = dy >= 0.0 ? 1.0 : -1.0;
      *penetration = overlap_y;
    }
    return 1;
  }

  const AnvilPhysicsBody *circle = a->shape == ANVIL_PHYSICS_CIRCLE ? a : b;
  const AnvilPhysicsBody *box = a->shape == ANVIL_PHYSICS_BOX ? a : b;
  double closest_x = fmax(box->x - box->half_width,
                          fmin(circle->x, box->x + box->half_width));
  double closest_y = fmax(box->y - box->half_height,
                          fmin(circle->y, box->y + box->half_height));
  double dx = closest_x - circle->x, dy = closest_y - circle->y;
  double distance_sq = dx * dx + dy * dy;
  if (distance_sq >= circle->radius * circle->radius)
    return 0;
  if (distance_sq > 1.0e-24) {
    double distance = sqrt(distance_sq);
    *normal_x = dx / distance;
    *normal_y = dy / distance;
    *penetration = circle->radius - distance;
  } else {
    double left = circle->x - (box->x - box->half_width);
    double right = box->x + box->half_width - circle->x;
    double bottom = circle->y - (box->y - box->half_height);
    double top = box->y + box->half_height - circle->y;
    double nearest = left;
    *normal_x = 1.0;
    *normal_y = 0.0;
    if (right < nearest) {
      nearest = right;
      *normal_x = -1.0;
      *normal_y = 0.0;
    }
    if (bottom < nearest) {
      nearest = bottom;
      *normal_x = 0.0;
      *normal_y = 1.0;
    }
    if (top < nearest) {
      nearest = top;
      *normal_x = 0.0;
      *normal_y = -1.0;
    }
    *penetration = circle->radius + nearest;
  }
  if (a->shape == ANVIL_PHYSICS_BOX) {
    *normal_x = -*normal_x;
    *normal_y = -*normal_y;
  }
  return 1;
}

double anvil_body_collision(double first, double second) {
  int first_slot, second_slot;
  AnvilPhysicsBody *a = anvil_physics_body(first, &first_slot);
  AnvilPhysicsBody *b = anvil_physics_body(second, &second_slot);
  if (!a || !b || first_slot == second_slot)
    return 0.0;
  double normal_x, normal_y, penetration;
  return anvil_physics_contact(a, b, &normal_x, &normal_y, &penetration)
             ? 1.0
             : 0.0;
}

double anvil_physics_gravity(double x, double y) {
  if (!isfinite(x) || !isfinite(y) || fabs(x) > 1.0e6 || fabs(y) > 1.0e6)
    return 0.0;
  anvil_physics_gravity_x = x;
  anvil_physics_gravity_y = y;
  return 1.0;
}

double anvil_physics_step(void) {
  double dt = anvil_delta();
  if (!isfinite(dt) || dt <= 0.0 || dt > 0.25)
    dt = 1.0 / 60.0;

  int contact_count = 0;
  for (int i = 0; i < anvil_physics_active_capacity; ++i) {
    AnvilPhysicsBody *a = &anvil_physics_bodies[i];
    if (!a->active)
      continue;
    for (int j = i + 1; j < anvil_physics_active_capacity; ++j) {
      AnvilPhysicsBody *b = &anvil_physics_bodies[j];
      if (!b->active)
        continue;
      double normal_x, normal_y, penetration;
      if (anvil_physics_contact(a, b, &normal_x, &normal_y, &penetration))
        ++contact_count;
    }
  }

  for (int i = 0; i < anvil_physics_active_capacity; ++i) {
    AnvilPhysicsBody *body = &anvil_physics_bodies[i];
    if (!body->active)
      continue;
    if (body->mass > 0.0) {
      body->vx += (anvil_physics_gravity_x + body->force_x / body->mass) * dt;
      body->vy += (anvil_physics_gravity_y + body->force_y / body->mass) * dt;
      body->vx = fmax(-ANVIL_PHYSICS_MAX_SPEED,
                      fmin(ANVIL_PHYSICS_MAX_SPEED, body->vx));
      body->vy = fmax(-ANVIL_PHYSICS_MAX_SPEED,
                      fmin(ANVIL_PHYSICS_MAX_SPEED, body->vy));
      body->x += body->vx * dt;
      body->y += body->vy * dt;
      if (body->x > ANVIL_PHYSICS_MAX_COORDINATE) {
        body->x = ANVIL_PHYSICS_MAX_COORDINATE;
        body->vx = 0.0;
      } else if (body->x < -ANVIL_PHYSICS_MAX_COORDINATE) {
        body->x = -ANVIL_PHYSICS_MAX_COORDINATE;
        body->vx = 0.0;
      }
      if (body->y > ANVIL_PHYSICS_MAX_COORDINATE) {
        body->y = ANVIL_PHYSICS_MAX_COORDINATE;
        body->vy = 0.0;
      } else if (body->y < -ANVIL_PHYSICS_MAX_COORDINATE) {
        body->y = -ANVIL_PHYSICS_MAX_COORDINATE;
        body->vy = 0.0;
      }
      if (!isfinite(body->x) || !isfinite(body->y) || !isfinite(body->vx) ||
          !isfinite(body->vy)) {
        body->x = body->y = body->vx = body->vy = 0.0;
      }
    }
    body->force_x = 0.0;
    body->force_y = 0.0;
  }

  for (int iteration = 0; iteration < ANVIL_PHYSICS_SOLVER_ITERATIONS;
       ++iteration) {
    for (int i = 0; i < anvil_physics_active_capacity; ++i) {
      AnvilPhysicsBody *a = &anvil_physics_bodies[i];
      if (!a->active)
        continue;
      for (int j = i + 1; j < anvil_physics_active_capacity; ++j) {
        AnvilPhysicsBody *b = &anvil_physics_bodies[j];
        if (!b->active)
          continue;
        double nx, ny, penetration;
        if (!anvil_physics_contact(a, b, &nx, &ny, &penetration))
          continue;
        double inverse_a = a->mass > 0.0 ? 1.0 / a->mass : 0.0;
        double inverse_b = b->mass > 0.0 ? 1.0 / b->mass : 0.0;
        double inverse_sum = inverse_a + inverse_b;
        if (inverse_sum <= 0.0)
          continue;

        double correction = fmax(penetration - 0.0001, 0.0) * 0.8 / inverse_sum;
        a->x -= nx * correction * inverse_a;
        a->y -= ny * correction * inverse_a;
        b->x += nx * correction * inverse_b;
        b->y += ny * correction * inverse_b;

        double relative_x = b->vx - a->vx;
        double relative_y = b->vy - a->vy;
        double along_normal = relative_x * nx + relative_y * ny;
        double normal_impulse = 0.0;
        if (along_normal < 0.0) {
          double restitution = fmin(a->restitution, b->restitution);
          normal_impulse = -(1.0 + restitution) * along_normal / inverse_sum;
          a->vx -= normal_impulse * nx * inverse_a;
          a->vy -= normal_impulse * ny * inverse_a;
          b->vx += normal_impulse * nx * inverse_b;
          b->vy += normal_impulse * ny * inverse_b;
        }

        if (normal_impulse > 0.0) {
          relative_x = b->vx - a->vx;
          relative_y = b->vy - a->vy;
          double tangent_x = relative_x - (relative_x * nx + relative_y * ny) * nx;
          double tangent_y = relative_y - (relative_x * nx + relative_y * ny) * ny;
          double tangent_length = hypot(tangent_x, tangent_y);
          if (tangent_length > 1.0e-12) {
            tangent_x /= tangent_length;
            tangent_y /= tangent_length;
            double tangent_impulse = -(relative_x * tangent_x +
                                       relative_y * tangent_y) / inverse_sum;
            double coefficient = sqrt(a->friction * b->friction);
            double maximum = coefficient * normal_impulse;
            tangent_impulse = fmax(-maximum, fmin(tangent_impulse, maximum));
            a->vx -= tangent_impulse * tangent_x * inverse_a;
            a->vy -= tangent_impulse * tangent_y * inverse_a;
            b->vx += tangent_impulse * tangent_x * inverse_b;
            b->vy += tangent_impulse * tangent_y * inverse_b;
          }
        }
      }
    }
  }

  /* Collision impulses and positional corrections can exceed the integration
   * limits above. Reapply the public bounds after the solver has finished. */
  for (int i = 0; i < anvil_physics_active_capacity; ++i) {
    AnvilPhysicsBody *body = &anvil_physics_bodies[i];
    if (!body->active)
      continue;
    body->vx = fmax(-ANVIL_PHYSICS_MAX_SPEED,
                    fmin(ANVIL_PHYSICS_MAX_SPEED, body->vx));
    body->vy = fmax(-ANVIL_PHYSICS_MAX_SPEED,
                    fmin(ANVIL_PHYSICS_MAX_SPEED, body->vy));
    if (body->x > ANVIL_PHYSICS_MAX_COORDINATE) {
      body->x = ANVIL_PHYSICS_MAX_COORDINATE;
      body->vx = 0.0;
    } else if (body->x < -ANVIL_PHYSICS_MAX_COORDINATE) {
      body->x = -ANVIL_PHYSICS_MAX_COORDINATE;
      body->vx = 0.0;
    }
    if (body->y > ANVIL_PHYSICS_MAX_COORDINATE) {
      body->y = ANVIL_PHYSICS_MAX_COORDINATE;
      body->vy = 0.0;
    } else if (body->y < -ANVIL_PHYSICS_MAX_COORDINATE) {
      body->y = -ANVIL_PHYSICS_MAX_COORDINATE;
      body->vy = 0.0;
    }
    if (!isfinite(body->x) || !isfinite(body->y) || !isfinite(body->vx) ||
        !isfinite(body->vy)) {
      body->x = body->y = body->vx = body->vy = 0.0;
    }
  }
  return (double)contact_count;
}

