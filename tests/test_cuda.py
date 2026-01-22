import torch


def main() -> int:
    available = torch.cuda.is_available()
    count = torch.cuda.device_count()
    name = torch.cuda.get_device_name(0) if available and count > 0 else "N/A"
    torch_version = torch.__version__
    cuda_version = torch.version.cuda or "N/A"
    cudnn_version = torch.backends.cudnn.version() or "N/A"
    print(f"cuda_available={available}")
    print(f"cuda_device_count={count}")
    print(f"cuda_device_name={name}")
    print(f"torch_version={torch_version}")
    print(f"torch_cuda_version={cuda_version}")
    print(f"cudnn_version={cudnn_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
