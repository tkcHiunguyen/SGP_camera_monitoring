import torch


def main() -> int:
    available = torch.cuda.is_available()
    count = torch.cuda.device_count()
    name = torch.cuda.get_device_name(0) if available and count > 0 else "N/A"
    print(f"cuda_available={available}")
    print(f"cuda_device_count={count}")
    print(f"cuda_device_name={name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
