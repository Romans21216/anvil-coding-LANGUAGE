/* PCM WAV playback for the Anvil runtime.
 *
 * Scope is deliberately small and documented in docs/LANGUAGE.md: uncompressed
 * PCM WAV files (8- or 16-bit, mono or stereo) are loaded whole into memory and
 * played one at a time through the Windows multimedia layer. There is no
 * mixing, no streaming, no volume control and no music format support yet, so
 * a game that needs those must use the default C backend with an external
 * library until this module grows.
 */
#include "anvil_runtime.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>
#include <mmsystem.h>

#define ANVIL_SOUND_SLOTS 8

static unsigned char *anvil_sound_data[ANVIL_SOUND_SLOTS];
static unsigned int anvil_sound_length[ANVIL_SOUND_SLOTS];
static unsigned int anvil_sound_rate_hz[ANVIL_SOUND_SLOTS];

static unsigned int read_u32le(const unsigned char *bytes) {
  return (unsigned int)bytes[0] | ((unsigned int)bytes[1] << 8) |
         ((unsigned int)bytes[2] << 16) | ((unsigned int)bytes[3] << 24);
}

static unsigned int read_u16le(const unsigned char *bytes) {
  return (unsigned int)bytes[0] | ((unsigned int)bytes[1] << 8);
}

/* Validate the RIFF/WAVE structure and the PCM format chunk.
 *
 * Returns 1 when the buffer is a PCM WAV this module can play, 0 otherwise.
 * `*rate_out` receives the sample rate so the caller can report it. */
static int anvil_wav_format(const unsigned char *bytes, unsigned int length,
                            unsigned int *rate_out) {
  unsigned int offset;
  int found_format = 0;
  unsigned int channels;
  unsigned int bits;

  if (length < 44 || memcmp(bytes, "RIFF", 4) != 0 ||
      memcmp(bytes + 8, "WAVE", 4) != 0)
    return 0;

  offset = 12;
  while (offset + 8 <= length) {
    unsigned int chunk_length = read_u32le(bytes + offset + 4);
    const unsigned char *chunk = bytes + offset + 8;
    if (chunk_length > length - (offset + 8))
      return 0;
    if (memcmp(bytes + offset, "fmt ", 4) == 0) {
      if (chunk_length < 16)
        return 0;
      if (read_u16le(chunk) != 1) /* WAVE_FORMAT_PCM */
        return 0;
      channels = read_u16le(chunk + 2);
      if (channels != 1 && channels != 2)
        return 0;
      if (rate_out)
        *rate_out = read_u32le(chunk + 4);
      bits = read_u16le(chunk + 14);
      if (bits != 8 && bits != 16)
        return 0;
      found_format = 1;
    } else if (memcmp(bytes + offset, "data", 4) == 0) {
      if (!found_format)
        return 0;
      return 1;
    }
    offset += 8 + chunk_length + (chunk_length & 1u);
  }
  return 0;
}

double anvil_sound_load(const char *path) {
  FILE *file;
  long size;
  unsigned char *bytes;
  unsigned int rate = 0;
  int slot;

  if (!path || !*path)
    return 0.0;
  file = fopen(path, "rb");
  if (!file)
    return 0.0;
  if (fseek(file, 0, SEEK_END) != 0) {
    fclose(file);
    return 0.0;
  }
  size = ftell(file);
  if (size <= 0 || size > 32 * 1024 * 1024) {
    fclose(file);
    return 0.0;
  }
  rewind(file);
  bytes = (unsigned char *)malloc((size_t)size);
  if (!bytes) {
    fclose(file);
    return 0.0;
  }
  if (fread(bytes, 1, (size_t)size, file) != (size_t)size) {
    free(bytes);
    fclose(file);
    return 0.0;
  }
  fclose(file);
  if (!anvil_wav_format(bytes, (unsigned int)size, &rate)) {
    free(bytes);
    return 0.0;
  }
  for (slot = 0; slot < ANVIL_SOUND_SLOTS; ++slot) {
    if (!anvil_sound_data[slot]) {
      anvil_sound_data[slot] = bytes;
      anvil_sound_length[slot] = (unsigned int)size;
      anvil_sound_rate_hz[slot] = rate;
      return (double)(slot + 1);
    }
  }
  free(bytes);
  return 0.0;
}

double anvil_sound_play(double handle) {
  int slot = (int)handle - 1;
  if (slot < 0 || slot >= ANVIL_SOUND_SLOTS || !anvil_sound_data[slot])
    return 0.0;
  if (!PlaySoundA((LPCSTR)anvil_sound_data[slot], NULL,
                  SND_MEMORY | SND_ASYNC | SND_NODEFAULT))
    return 0.0;
  return 1.0;
}

double anvil_sound_stop(void) {
  PlaySoundA(NULL, NULL, 0);
  return 0.0;
}

double anvil_sound_rate(double handle) {
  int slot = (int)handle - 1;
  if (slot < 0 || slot >= ANVIL_SOUND_SLOTS || !anvil_sound_data[slot])
    return 0.0;
  return (double)anvil_sound_rate_hz[slot];
}

double anvil_sound_length_ms(double handle) {
  int slot = (int)handle - 1;
  if (slot < 0 || slot >= ANVIL_SOUND_SLOTS || !anvil_sound_data[slot])
    return 0.0;
  return (double)anvil_sound_length[slot];
}

void anvil_sound_release_all(void) {
  int slot;
  PlaySoundA(NULL, NULL, 0);
  for (slot = 0; slot < ANVIL_SOUND_SLOTS; ++slot) {
    free(anvil_sound_data[slot]);
    anvil_sound_data[slot] = NULL;
    anvil_sound_length[slot] = 0;
    anvil_sound_rate_hz[slot] = 0;
  }
}
