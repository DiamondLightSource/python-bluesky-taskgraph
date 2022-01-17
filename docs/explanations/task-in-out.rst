Why are Task in/out names defined by the TaskGraph?
==============================

Task input and output names are defined by the TaskGraph they are in to allow task definitions to be reused between
multiple taskgraphs without any forethought about where their inputs/outputs are being routed.

e.g. a Task with input "wavelength" and output "refined_wavelength" that iteratively refines the limits of the input
value may have its output used for a function that requires a wavelength value that would otherwise require overriding
the initial wavelength value, or adjusting the refining task to call its input "initial_wavelength".

This also aims to prevent the confusion of exactly what "wavelength" refers to: is it the current wavelength value, a
device that controls wavelength, a target value etc.

