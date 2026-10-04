//! Linux input mappings plus heap cleanup. This does not lock all Qt/library/stack
//! memory, erase previous swap, or provide protection against root/hibernation.
use crate::{Error, Result};
use std::alloc::{GlobalAlloc, Layout, System};
use zeroize::Zeroize;

pub struct WipingAllocator;
// SAFETY: delegating allocation layout/alignment to System; wiping is performed
// only while owning a live allocation, before returning it to System.
unsafe impl GlobalAlloc for WipingAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        unsafe { System.alloc(layout) }
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        unsafe { System.alloc_zeroed(layout) }
    }
    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { libc::explicit_bzero(ptr.cast(), layout.size()) };
        unsafe { System.dealloc(ptr, layout) };
    }
    unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        let Ok(new_layout) = Layout::from_size_align(size, layout.align()) else {
            return std::ptr::null_mut();
        };
        let replacement = unsafe { System.alloc(new_layout) };
        if replacement.is_null() {
            return replacement;
        }
        unsafe {
            std::ptr::copy_nonoverlapping(ptr, replacement, layout.size().min(size));
            self.dealloc(ptr, layout)
        };
        replacement
    }
}
/// A dedicated mapping: never shares a locked page with a different allocation.
pub struct LockedBytes {
    pointer: *mut u8,
    size: usize,
}
impl LockedBytes {
    pub fn new(size: usize) -> Result<Self> {
        if size == 0 || size > 4 * 1024 * 1024 {
            return Err(Error::Limit);
        }
        // SAFETY: anonymous private mapping; fd/offset ignored; owned until Drop.
        let pointer = unsafe {
            libc::mmap(
                std::ptr::null_mut(),
                size,
                libc::PROT_READ | libc::PROT_WRITE,
                libc::MAP_PRIVATE | libc::MAP_ANONYMOUS,
                -1,
                0,
            )
        };
        if pointer == libc::MAP_FAILED {
            return Err(Error::MemoryProtection);
        }
        if unsafe { libc::mlock(pointer, size) } != 0
            || unsafe { libc::madvise(pointer, size, libc::MADV_DONTDUMP) } != 0
        {
            unsafe { libc::munmap(pointer, size) };
            return Err(Error::MemoryProtection);
        }
        Ok(Self {
            pointer: pointer.cast(),
            size,
        })
    }
    pub fn bytes_mut(&mut self) -> &mut [u8] {
        unsafe { std::slice::from_raw_parts_mut(self.pointer, self.size) }
    }
    pub fn bytes(&self) -> &[u8] {
        unsafe { std::slice::from_raw_parts(self.pointer, self.size) }
    }
}
impl Drop for LockedBytes {
    fn drop(&mut self) {
        self.bytes_mut().zeroize();
        // munmap releases the dedicated pages and their lock atomically.
        unsafe { libc::munmap(self.pointer.cast(), self.size) };
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn locked_mapping_has_independent_pages_and_is_zero_initialized() {
        let mut a = LockedBytes::new(64).unwrap();
        let mut b = LockedBytes::new(64).unwrap();
        assert!(a.bytes().iter().all(|v| *v == 0));
        a.bytes_mut().fill(42);
        b.bytes_mut().fill(99);
        assert_ne!(a.pointer, b.pointer);
        drop(a);
        assert!(b.bytes().iter().all(|v| *v == 99));
    }
    #[test]
    fn realloc_keeps_alignment_data_and_original_on_failure() {
        unsafe {
            let layout = Layout::from_size_align(128, 64).unwrap();
            let p = WipingAllocator.alloc(layout);
            assert!(!p.is_null());
            std::ptr::write_bytes(p, 42, 128);
            let q = WipingAllocator.realloc(p, layout, 256);
            assert!(!q.is_null());
            assert_eq!(q as usize % 64, 0);
            assert!(std::slice::from_raw_parts(q, 128).iter().all(|v| *v == 42));
            let layout = Layout::from_size_align(256, 64).unwrap();
            assert!(WipingAllocator.realloc(q, layout, usize::MAX).is_null());
            assert!(std::slice::from_raw_parts(q, 128).iter().all(|v| *v == 42));
            WipingAllocator.dealloc(q, layout);
        }
    }
}
